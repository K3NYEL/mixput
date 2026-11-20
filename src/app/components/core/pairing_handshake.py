"""Small, bounded plaintext control frames used only before secure pairing."""
import base64
import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.components.core.input_protocol import ProtocolError

PAIRING_VERSION = 1
MAX_CONTROL_BYTES = 4096


def send_control(connection, message):
    payload = json.dumps(message, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    if len(payload) > MAX_CONTROL_BYTES:
        raise ProtocolError("Pairing control message is too large.")
    connection.sendall(payload + b"\n")


def receive_control(connection):
    buffer = bytearray()
    while len(buffer) <= MAX_CONTROL_BYTES:
        chunk = connection.recv(1024)
        if not chunk:
            raise ProtocolError("Connection closed during pairing.")
        marker = chunk.find(b"\n")
        if marker >= 0:
            buffer.extend(chunk[:marker])
            if marker + 1 < len(chunk):
                raise ProtocolError("Unexpected data after pairing control frame.")
            try:
                value = json.loads(buffer.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ProtocolError("Invalid pairing control message.") from error
            if not isinstance(value, dict):
                raise ProtocolError("Invalid pairing control message.")
            return value
        buffer.extend(chunk)
    raise ProtocolError("Pairing control message is too large.")


def new_ephemeral_key():
    private = X25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private, base64.b64encode(public).decode("ascii")


def derive_pairing_key(private, peer_public_text, salt):
    try:
        peer_bytes = base64.b64decode(peer_public_text, validate=True)
        peer = X25519PublicKey.from_public_bytes(peer_bytes)
    except (ValueError, TypeError) as error:
        raise ProtocolError("Invalid pairing public key.") from error
    shared = private.exchange(peer)
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"mixput-pairing-v1",
    ).derive(shared)


def encrypt_session_token(pairing_key, token):
    nonce = os.urandom(12)
    ciphertext = AESGCM(pairing_key).encrypt(nonce, token.encode("ascii"), b"mixput-session-key")
    return base64.b64encode(nonce).decode("ascii"), base64.b64encode(ciphertext).decode("ascii")


def decrypt_session_token(pairing_key, nonce_text, ciphertext_text):
    try:
        nonce = base64.b64decode(nonce_text, validate=True)
        ciphertext = base64.b64decode(ciphertext_text, validate=True)
        token = AESGCM(pairing_key).decrypt(nonce, ciphertext, b"mixput-session-key")
        return token.decode("ascii")
    except Exception as error:
        raise ProtocolError("Could not securely complete device pairing.") from error
