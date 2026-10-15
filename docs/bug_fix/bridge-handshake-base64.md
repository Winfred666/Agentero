# Relay handshake key encoding

The relay requires canonical padded standard Base64 for `e2ee_hello.key`; base64url caused policy close `1008 Invalid handshake key`. The client now sends standard Base64, and the host accepts both standard and legacy unpadded base64url. Pairing, signatures and encrypted frames are unchanged.

`handshake_key_uses_relay_base64_and_accepts_legacy_encoding` covers the wire encoding, legacy keys, malformed input and wrong length:

```sh
cargo test -p agentero integration::bridge::crypto::tests --lib
```

Both host and iOS client must be updated: old hosts cannot decode the new encoding. Full app builds and real-device pairing/reconnect still need verification.
