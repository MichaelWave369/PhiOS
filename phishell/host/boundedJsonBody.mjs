export async function readBoundedJsonObject(request, { maxBytes = 65536 } = {}) {
  const rawLength = request.headers["content-length"];
  const declared = Number(rawLength);
  if (!Number.isInteger(declared) || declared < 2 || declared > maxBytes) {
    throw new Error("invalid_bounded_json_length");
  }

  const chunks = [];
  let received = 0;
  for await (const chunk of request) {
    received += chunk.length;
    if (received > maxBytes) {
      throw new Error("bounded_json_body_too_large");
    }
    chunks.push(chunk);
  }

  if (received !== declared) {
    throw new Error("bounded_json_length_mismatch");
  }

  const parsed = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("bounded_json_body_must_be_object");
  }
  return parsed;
}
