use crate::core::error::AppError;
use futures_util::{SinkExt, StreamExt};
use tokio::net::TcpStream;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::{connect_async, MaybeTlsStream, WebSocketStream};
use url::Url;

pub type RelaySocket = WebSocketStream<MaybeTlsStream<TcpStream>>;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RelayFrame {
    Text(String),
    Binary(Vec<u8>),
    Close,
}

/// Connect to a Paseo-compatible Relay. The caller builds role-specific URLs
/// with [`crate::integration::bridge::RelayEndpoint::connection_url`].
pub async fn connect_relay(url: Url) -> Result<RelaySocket, AppError> {
    let (socket, response) = connect_async(url.as_str())
        .await
        .map_err(|error| AppError::message(format!("Relay connection failed: {error}")))?;
    if response.status().as_u16() != 101 {
        return Err(AppError::message(format!(
            "Relay rejected WebSocket upgrade with HTTP {}",
            response.status()
        )));
    }
    Ok(socket)
}

pub async fn send_text(socket: &mut RelaySocket, value: impl Into<String>) -> Result<(), AppError> {
    socket
        .send(Message::Text(value.into().into()))
        .await
        .map_err(|error| AppError::message(format!("Relay write failed: {error}")))
}

pub async fn send_binary(socket: &mut RelaySocket, value: Vec<u8>) -> Result<(), AppError> {
    socket
        .send(Message::Binary(value.into()))
        .await
        .map_err(|error| AppError::message(format!("Relay write failed: {error}")))
}

/// Reads the next application frame. WebSocket ping/pong is answered here so
/// every Bridge loop gets transport-level keepalive behavior automatically.
pub async fn next_frame(socket: &mut RelaySocket) -> Result<RelayFrame, AppError> {
    loop {
        let Some(message) = socket.next().await else {
            return Ok(RelayFrame::Close);
        };
        let message =
            message.map_err(|error| AppError::message(format!("Relay read failed: {error}")))?;
        match message {
            Message::Text(value) => return Ok(RelayFrame::Text(value.to_string())),
            Message::Binary(value) => return Ok(RelayFrame::Binary(value.to_vec())),
            Message::Ping(payload) => {
                socket
                    .send(Message::Pong(payload))
                    .await
                    .map_err(|error| AppError::message(format!("Relay pong failed: {error}")))?;
            }
            Message::Close(Some(frame)) => {
                return Err(AppError::message(format!(
                    "Relay closed ({}): {}",
                    frame.code, frame.reason
                )));
            }
            Message::Close(None) => return Ok(RelayFrame::Close),
            Message::Pong(_) | Message::Frame(_) => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::net::TcpListener;
    use tokio_tungstenite::accept_async;
    use tokio_tungstenite::tungstenite::protocol::CloseFrame;

    #[tokio::test]
    async fn preserves_close_code_and_reason_from_websocket() {
        for (code, reason) in [
            (1008_u16, "Invalid handshake key"),
            (1013, "Data route unavailable"),
        ] {
            let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
            let url = Url::parse(&format!("ws://{}", listener.local_addr().unwrap())).unwrap();
            let server = tokio::spawn(async move {
                let (stream, _) = listener.accept().await.unwrap();
                let mut socket = accept_async(stream).await.unwrap();
                socket
                    .close(Some(CloseFrame {
                        code: code.into(),
                        reason: reason.into(),
                    }))
                    .await
                    .unwrap();
            });
            let mut socket = connect_relay(url).await.unwrap();
            let error =
                tokio::time::timeout(std::time::Duration::from_secs(5), next_frame(&mut socket))
                    .await
                    .unwrap()
                    .unwrap_err();
            assert_eq!(
                error.to_string(),
                format!("Relay closed ({code}): {reason}")
            );
            server.await.unwrap();
        }
    }
}
