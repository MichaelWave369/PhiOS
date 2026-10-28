/*
 * PhiOS Sovereignty E0: narrow Linux x86_64 seccomp experiment.
 * An experimental executable, NOT an OS network sandbox or a shipping policy.
 * Compile: cc -std=c11 -O2 -Wall -Wextra -Werror -o e0_probe e0_probe.c
 *
 * The trusted parent creates a Unix stream socketpair before fork.
 * The child applies an inherited kernel seccomp filter denying socket creation
 * and selected network operations. The child then deliberately attempts raw
 * IPv4, IPv6, and UDS sockets. A preopened descriptor still supports IPC.
 *
 * This demonstrates only the enumerated syscall denials. It does NOT prove
 * network egress isolation against inherited IP FDs, io_uring, alternate ABIs,
 * privileged escape, or uncontained launch paths.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#if !defined(__linux__) || !defined(__x86_64__)
#error "E0 demonstration supports Linux x86_64 only; other architectures unverified"
#endif

#define DENY_NR(n) \
    BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_##n, 0, 1), \
    BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | (EACCES & SECCOMP_RET_DATA))

struct observed {
    int ipv4_denied;
    int ipv6_denied;
    int uds_creation_denied;
    int child_seccomp_installed;
};

static int install_filter(void) {
    struct sock_filter instructions[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        /* Also reject x32 ABI syscall numbers for this x86_64-only experiment. */
        BPF_JUMP(BPF_JMP | BPF_JGE | BPF_K, 0x40000000U, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        DENY_NR(socket),
        DENY_NR(socketpair),
        DENY_NR(connect),
        DENY_NR(bind),
        DENY_NR(listen),
        DENY_NR(accept),
        DENY_NR(accept4),
        DENY_NR(sendto),
        DENY_NR(sendmsg),
        DENY_NR(recvmsg),
        DENY_NR(setsockopt),
        DENY_NR(getsockopt),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog program = {
        .len = (unsigned short)(sizeof instructions / sizeof instructions[0]),
        .filter = instructions
    };
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) return -1;
    return prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program);
}

static int new_socket_denied(int family) {
    errno = 0;
    int fd = socket(family, SOCK_STREAM, 0);
    int saved_errno = errno;
    if (fd >= 0) close(fd);
    return fd == -1 && saved_errno == EACCES;
}

static int write_exact(int fd, const void *buf, size_t n) {
    const char *p = (const char *)buf;
    while (n) {
        ssize_t count = write(fd, p, n);
        if (count <= 0) return -1;
        p += count;
        n -= (size_t)count;
    }
    return 0;
}

static int read_exact(int fd, void *buf, size_t n) {
    char *p = (char *)buf;
    while (n) {
        ssize_t count = read(fd, p, n);
        if (count <= 0) return -1;
        p += count;
        n -= (size_t)count;
    }
    return 0;
}

int main(void) {
    int pair[2] = {-1, -1};
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, pair) != 0) {
        perror("parent socketpair");
        return 2;
    }

    pid_t child = fork();
    if (child < 0) {
        perror("fork");
        return 3;
    }
    if (child == 0) {
        close(pair[0]);
        /* This sample clears other high descriptors to avoid accidental
         * inherited networking; this is NOT a general-purpose FD audit. */
        for (int fd = 3; fd < 256; ++fd) {
            if (fd != pair[1]) close(fd);
        }
        struct observed result = {0, 0, 0, 0};
        if (install_filter() != 0) {
            perror("seccomp install");
            _exit(4);
        }
        result.child_seccomp_installed = 1;
        result.ipv4_denied = new_socket_denied(AF_INET);
        result.ipv6_denied = new_socket_denied(AF_INET6);
        result.uds_creation_denied = new_socket_denied(AF_UNIX);
        if (write_exact(pair[1], &result, sizeof result) != 0) _exit(5);
        char ack = 0;
        if (read_exact(pair[1], &ack, 1) != 0 || ack != 'K') _exit(6);
        close(pair[1]);
        _exit(result.ipv4_denied && result.ipv6_denied &&
              result.uds_creation_denied ? 0 : 7);
    }

    close(pair[1]);
    struct observed proof = {0, 0, 0, 0};
    int received = read_exact(pair[0], &proof, sizeof proof) == 0;
    int acknowledged = received && write_exact(pair[0], "K", 1) == 0;
    close(pair[0]);
    int status = 0;
    if (waitpid(child, &status, 0) != child) {
        perror("waitpid");
        return 8;
    }
    int child_ok = WIFEXITED(status) && WEXITSTATUS(status) == 0;
    int verified = received && acknowledged && child_ok &&
        proof.child_seccomp_installed && proof.ipv4_denied &&
        proof.ipv6_denied && proof.uds_creation_denied;

    printf("{\"schema\":\"PHIOS_SOVEREIGNTY_E0_V1\","
           "\"platform\":\"linux_x86_64\","
           "\"scope\":\"single_process_syscall_denials_and_preopened_uds\","
           "\"kernel_seccomp_installed\":%s,"
           "\"raw_ipv4_socket_denied\":%s,"
           "\"raw_ipv6_socket_denied\":%s,"
           "\"new_uds_socket_denied\":%s,"
           "\"preopened_uds_ipc_passed\":%s,"
           "\"independent_packet_capture_performed\":false,"
           "\"inherited_ip_fd_escape_tested\":false,"
           "\"full_os_network_isolation_verified\":false,"
           "\"status\":\"%s\"}\n",
           proof.child_seccomp_installed ? "true" : "false",
           proof.ipv4_denied ? "true" : "false",
           proof.ipv6_denied ? "true" : "false",
           proof.uds_creation_denied ? "true" : "false",
           acknowledged ? "true" : "false",
           verified ? "PASS" : "FAIL");
    return verified ? 0 : 9;
}
