use crate::core::error::AppError;
use base64::engine::general_purpose::{STANDARD, URL_SAFE_NO_PAD};
use base64::Engine;
use crypto_box::aead::{Aead, AeadCore, OsRng};
use crypto_box::{PublicKey, SalsaBox, SecretKey};

const NONCE_BYTES: usize = 24;

/// Relay validation requires canonical padded standard Base64, not base64url.
pub fn encode_handshake_key(public: &PublicKey) -> String {
    STANDARD.encode(public.as_bytes())
}

/// Accept new relay-compatible keys and keys sent by older Agentero clients.
pub fn decode_handshake_key(value: &str) -> Result<PublicKey, AppError> {
    let bytes = STANDARD
        .decode(value)
        .or_else(|_| URL_SAFE_NO_PAD.decode(value))
        .map_err(|_| AppError::message("E2EE public key is not valid base64"))?;
    let bytes: [u8; 32] = bytes
        .try_into()
        .map_err(|_| AppError::message("E2EE public key must contain 32 bytes"))?;
    Ok(PublicKey::from(bytes))
}

/// Encrypts and decrypts one Bridge data-channel frame.
///
/// The frame format is `[24-byte nonce][XSalsa20-Poly1305 ciphertext]`. Relay
/// routing is deliberately outside this type and therefore never receives the
/// plaintext or either endpoint's long-term private key.
pub struct SessionCipher {
    cipher: SalsaBox,
}

impl SessionCipher {
    pub fn from_keys(local_secret: &SecretKey, remote_public: &PublicKey) -> Self {
        Self {
            cipher: SalsaBox::new(remote_public, local_secret),
        }
    }

    pub fn encrypt(&self, plaintext: &[u8]) -> Result<Vec<u8>, AppError> {
        let nonce = SalsaBox::generate_nonce(&mut OsRng);
        let ciphertext = self
            .cipher
            .encrypt(&nonce, plaintext)
            .map_err(|_| AppError::message("Bridge frame encryption failed"))?;
        let mut frame = Vec::with_capacity(nonce.len() + ciphertext.len());
        frame.extend_from_slice(&nonce);
        frame.extend_from_slice(&ciphertext);
        Ok(frame)
    }

    pub fn decrypt(&self, frame: &[u8]) -> Result<Vec<u8>, AppError> {
        if frame.len() <= NONCE_BYTES {
            return Err(AppError::message("Bridge encrypted frame is too short"));
        }
        let (nonce, ciphertext) = frame.split_at(NONCE_BYTES);
        self.cipher
            .decrypt(nonce.into(), ciphertext)
            .map_err(|_| AppError::message("Bridge frame authentication failed"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn handshake_key_uses_relay_base64_and_accepts_legacy_encoding() {
        let public = PublicKey::from([251_u8; 32]);
        let encoded = encode_handshake_key(&public);
        assert!(encoded.ends_with('='));
        assert!(encoded.contains('+') || encoded.contains('/'));
        assert_eq!(STANDARD.decode(&encoded).unwrap(), public.as_bytes());
        assert_eq!(decode_handshake_key(&encoded).unwrap(), public);
        assert_eq!(
            decode_handshake_key(&URL_SAFE_NO_PAD.encode(public.as_bytes())).unwrap(),
            public
        );
        assert!(decode_handshake_key("!").is_err());
        assert!(decode_handshake_key(&STANDARD.encode([1_u8; 31])).is_err());
    }

    #[test]
    fn encrypts_a_frame_that_only_the_other_endpoint_can_open() {
        let left = SecretKey::generate(&mut OsRng);
        let right = SecretKey::generate(&mut OsRng);
        let sender = SessionCipher::from_keys(&left, &right.public_key());
        let receiver = SessionCipher::from_keys(&right, &left.public_key());

        let encrypted = sender.encrypt(b"bridge rpc").expect("encrypt frame");
        assert_ne!(encrypted, b"bridge rpc");
        assert_eq!(
            receiver.decrypt(&encrypted).expect("decrypt frame"),
            b"bridge rpc"
        );
    }

    #[test]
    fn rejects_a_tampered_frame() {
        let left = SecretKey::generate(&mut OsRng);
        let right = SecretKey::generate(&mut OsRng);
        let sender = SessionCipher::from_keys(&left, &right.public_key());
        let receiver = SessionCipher::from_keys(&right, &left.public_key());
        let mut encrypted = sender.encrypt(b"bridge rpc").expect("encrypt frame");
        let last = encrypted.last_mut().expect("ciphertext is not empty");
        *last ^= 1;

        assert!(receiver.decrypt(&encrypted).is_err());
    }
}
