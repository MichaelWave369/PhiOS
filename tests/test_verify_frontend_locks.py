import copy
import unittest

from scripts.verify_frontend_locks import validate_lock, APPROVED

class LockGuardTests(unittest.TestCase):
    def make_graph(self):
        pkg = {
            "name": "unit-test", "version": "0.1.0",
            "dependencies": {"example": "^2.0.0"}, "devDependencies": {}
        }
        graph = {
            "name": "unit-test", "version": "0.1.0", "lockfileVersion": 3,
            "requires": True,
            "packages": {
                "": copy.deepcopy(pkg),
                "node_modules/example": {
                    "version": "2.0.0",
                    "resolved": "https://registry.npmjs.org/example/-/example-2.0.0.tgz",
                    "integrity": "sha512-" + "A" * 60,
                }
            }
        }
        return pkg,graph

    def test_valid_locked_graph(self):
        pkg,graph=self.make_graph()
        self.assertEqual(validate_lock(graph,pkg),1)
        self.assertEqual(set(APPROVED),{"vessie-web","thinktank-web"})

    def test_bogus_registry_refused(self):
        pkg,graph=self.make_graph()
        graph["packages"]["node_modules/example"]["resolved"] = "https://evil.invalid/x"
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_REGISTRY"):
            validate_lock(graph,pkg)

    def test_missing_integrity_refused(self):
        pkg,graph=self.make_graph()
        del graph["packages"]["node_modules/example"]["integrity"]
        with self.assertRaisesRegex(ValueError,"INTEGRITY_MISSING"):
            validate_lock(graph,pkg)

    def test_root_manifest_drift_refused(self):
        pkg,graph=self.make_graph()
        graph["packages"][""]["dependencies"]["example"]="^9.0.0"
        with self.assertRaisesRegex(ValueError,"ROOT_DRIFT"):
            validate_lock(graph,pkg)

    def test_path_traversal_refused(self):
        pkg,graph=self.make_graph()
        graph["packages"]["node_modules/../unsafe"]=graph["packages"].pop("node_modules/example")
        with self.assertRaisesRegex(ValueError,"UNSAFE_PACKAGE_PATH"):
            validate_lock(graph,pkg)

    def test_missing_package_graph_and_old_locks_refused(self):
        pkg,graph=self.make_graph()
        graph["lockfileVersion"]=2
        with self.assertRaisesRegex(ValueError,"LOCKFILE_VERSION"):
            validate_lock(graph,pkg)

if __name__=="__main__":
    unittest.main()
