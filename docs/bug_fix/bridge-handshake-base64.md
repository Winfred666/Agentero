# Relay handshake key encoding

The relay validates `e2ee_hello.key` as canonical padded standard Base64.
Agentero previously sent URL-safe unpadded Base64, causing a policy close
(`1008 Invalid handshake key`) before E2EE was established.

The client now encodes only the ephemeral handshake public key with standard
Base64. The host accepts both standard Base64 and legacy unpadded base64url.
Pairing offers, identity files, device signatures and encrypted frames are
unchanged. No authentication checks are bypassed.

Regression: `handshake_key_uses_relay_base64_and_accepts_legacy_encoding` in
`src-tauri/src/integration/bridge/crypto.rs` checks the wire encoding, legacy
compatibility, malformed input and wrong key length. Existing crypto tests
continue to check encryption and tamper rejection.

Run on a configured desktop build environment:

```sh
cargo test -p agentero integration::bridge::crypto::tests --lib
```

Release verification requires both an updated host and an updated iOS client.
Old desktop hosts cannot decode the new standard Base64 handshake. A mobile
binary build and real-device smoke test are still required on macOS.
