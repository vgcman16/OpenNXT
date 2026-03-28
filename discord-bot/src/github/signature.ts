import crypto from "node:crypto";

export function verifyGithubSignature(secret: string, payload: Buffer, signatureHeader?: string | string[]) {
  if (!signatureHeader || Array.isArray(signatureHeader)) {
    return false;
  }

  const expected = `sha256=${crypto.createHmac("sha256", secret).update(payload).digest("hex")}`;
  const expectedBuffer = Buffer.from(expected, "utf8");
  const actualBuffer = Buffer.from(signatureHeader, "utf8");

  if (expectedBuffer.length !== actualBuffer.length) {
    return false;
  }

  return crypto.timingSafeEqual(expectedBuffer, actualBuffer);
}
