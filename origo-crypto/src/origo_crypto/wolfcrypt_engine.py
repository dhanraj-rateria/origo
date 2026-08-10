"""ctypes bindings against libwolfssl.so."""

from __future__ import annotations

import ctypes
from ctypes import POINTER, byref, c_int, c_ubyte, c_uint32, create_string_buffer, sizeof

from .engine import EncapsResult, KemKeypair

_lib = ctypes.CDLL("libwolfssl.so")   # adjust to your build: .dylib on macOS, a full
                                       # path if not on the linker's default search path

WC_ML_KEM_1024 = 3        # VERIFY: the WC_ML_KEM_* enum values in wolfssl/wolfcrypt/mlkem.h
ML_KEM_1024_PUBLIC_KEY_BYTES = 1568
ML_KEM_1024_PRIVATE_KEY_BYTES = 3168
ML_KEM_1024_CIPHERTEXT_BYTES = 1568
ML_KEM_SS_BYTES = 32

ML_DSA_LEVEL_5 = 5        # VERIFY: matches your build's ML-DSA-87 / Category-5 constant


class _MlKemKey(ctypes.Structure):
    _fields_ = [("_opaque", ctypes.c_byte * 4096)]   # oversized on purpose — the real
                                                       # struct layout is internal to
                                                       # wolfCrypt; this only needs to be
                                                       # large enough, never read directly


class _MlDsaKey(ctypes.Structure):
    _fields_ = [("_opaque", ctypes.c_byte * 8192)]


def _check(rc: int, op: str) -> None:
    if rc != 0:
        raise RuntimeError(f"wolfCrypt {op} failed, rc={rc}")


class WolfCryptEngine:
    def __init__(self) -> None:
        self._rng = ctypes.create_string_buffer(256)   # oversized WC_RNG buffer
        _check(_lib.wc_InitRng(byref(self._rng)), "wc_InitRng")

    def random_bytes(self, n: int) -> bytes:
        buf = create_string_buffer(n)
        _check(_lib.wc_RNG_GenerateBlock(byref(self._rng), buf, c_uint32(n)), "wc_RNG_GenerateBlock")
        return buf.raw[:n]

    # ---------------------------------------------------------------- ML-KEM

    def kem_keygen(self) -> KemKeypair:
        key = _MlKemKey()
        _check(_lib.wc_MlKemKey_Init(byref(key), WC_ML_KEM_1024, None, -2,), "wc_MlKemKey_Init")
        try:
            _check(_lib.wc_MlKemKey_MakeKey(byref(key), byref(self._rng)), "wc_MlKemKey_MakeKey")
            ek = create_string_buffer(ML_KEM_1024_PUBLIC_KEY_BYTES)
            dk = create_string_buffer(ML_KEM_1024_PRIVATE_KEY_BYTES)
            _check(_lib.wc_MlKemKey_EncodePublicKey(byref(key), ek, c_uint32(len(ek))), "EncodePublicKey")
            _check(_lib.wc_MlKemKey_EncodePrivateKey(byref(key), dk, c_uint32(len(dk))), "EncodePrivateKey")
            return KemKeypair(ek=ek.raw[:ML_KEM_1024_PUBLIC_KEY_BYTES], dk=dk.raw[:ML_KEM_1024_PRIVATE_KEY_BYTES])
        finally:
            _lib.wc_MlKemKey_Free(byref(key))

    def kem_encapsulate(self, ek: bytes) -> EncapsResult:
        key = _MlKemKey()
        _check(_lib.wc_MlKemKey_Init(byref(key), None, -2, WC_ML_KEM_1024), "Init")
        try:
            _check(_lib.wc_MlKemKey_DecodePublicKey(byref(key), ek, c_uint32(len(ek))), "DecodePublicKey")
            ct = create_string_buffer(ML_KEM_1024_CIPHERTEXT_BYTES)
            ss = create_string_buffer(ML_KEM_SS_BYTES)
            _check(_lib.wc_MlKemKey_Encapsulate(byref(key), ct, ss, byref(self._rng)), "Encapsulate")
            return EncapsResult(ciphertext=ct.raw[:ML_KEM_1024_CIPHERTEXT_BYTES], shared_secret=ss.raw[:ML_KEM_SS_BYTES])
        finally:
            _lib.wc_MlKemKey_Free(byref(key))

    def kem_decapsulate(self, dk: bytes, ciphertext: bytes) -> bytes:
        key = _MlKemKey()
        _check(_lib.wc_MlKemKey_Init(byref(key), None, -2, WC_ML_KEM_1024), "Init")
        try:
            _check(_lib.wc_MlKemKey_DecodePrivateKey(byref(key), dk, c_uint32(len(dk))), "DecodePrivateKey")
            ss = create_string_buffer(ML_KEM_SS_BYTES)
            _check(_lib.wc_MlKemKey_Decapsulate(byref(key), ss, ciphertext, c_uint32(len(ciphertext))), "Decapsulate")
            return ss.raw[:ML_KEM_SS_BYTES]
        finally:
            _lib.wc_MlKemKey_Free(byref(key))

    # ---------------------------------------------------------------- ML-DSA

    def dsa_keygen(self) -> tuple[bytes, bytes]:
        key = _MlDsaKey()
        _check(_lib.wc_MlDsaKey_Init(byref(key), None, -2), "wc_MlDsaKey_Init")
        try:
            _check(_lib.wc_MlDsaKey_SetLevel(byref(key), c_int(ML_DSA_LEVEL_5)), "SetLevel")
            _check(_lib.wc_MlDsaKey_MakeKey(byref(key), byref(self._rng)), "MakeKey")
            pub, priv = create_string_buffer(2592), create_string_buffer(4896)   # ML-DSA-87 sizes — VERIFY
            _check(_lib.wc_MlDsaKey_EncodePublicKey(byref(key), pub, c_uint32(len(pub))), "EncodePublicKey")
            _check(_lib.wc_MlDsaKey_EncodePrivateKey(byref(key), priv, c_uint32(len(priv))), "EncodePrivateKey")
            return pub.raw[:2592], priv.raw[:4896]
        finally:
            _lib.wc_MlDsaKey_Free(byref(key))

    def dsa_sign(self, *, private_key: bytes, message: bytes) -> bytes:
        key = _MlDsaKey()
        _check(_lib.wc_MlDsaKey_Init(byref(key), None, -2), "Init")
        try:
            _check(_lib.wc_MlDsaKey_SetLevel(byref(key), c_int(ML_DSA_LEVEL_5)), "SetLevel")
            _check(_lib.wc_MlDsaKey_DecodePrivateKey(byref(key), private_key, c_uint32(len(private_key))), "DecodePrivateKey")
            sig = create_string_buffer(4627)   # ML-DSA-87 signature size — VERIFY
            sig_len = c_uint32(len(sig))
            _check(_lib.wc_MlDsaKey_Sign(byref(key), sig, byref(sig_len), message, c_uint32(len(message)), byref(self._rng)), "Sign")
            return sig.raw[: sig_len.value]
        finally:
            _lib.wc_MlDsaKey_Free(byref(key))

    def dsa_verify(self, *, public_key: bytes, message: bytes, signature: bytes) -> bool:
        key = _MlDsaKey()
        _check(_lib.wc_MlDsaKey_Init(byref(key), None, -2), "Init")
        try:
            _check(_lib.wc_MlDsaKey_SetLevel(byref(key), c_int(ML_DSA_LEVEL_5)), "SetLevel")
            _check(_lib.wc_MlDsaKey_DecodePublicKey(byref(key), public_key, c_uint32(len(public_key))), "DecodePublicKey")
            result = c_int(0)
            rc = _lib.wc_MlDsaKey_Verify(byref(key), signature, c_uint32(len(signature)), message, c_uint32(len(message)), byref(result))
            return rc == 0 and result.value == 1
        finally:
            _lib.wc_MlDsaKey_Free(byref(key))

    # ---------------------------------------------------------------- AEAD + HKDF (high confidence)

    def aead_encrypt(self, *, key: bytes, nonce: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
        aes = ctypes.create_string_buffer(512)   # oversized Aes struct
        _check(_lib.wc_AesGcmSetKey(byref(aes), key, c_uint32(len(key))), "wc_AesGcmSetKey")
        out = create_string_buffer(len(plaintext))
        tag = create_string_buffer(16)
        _check(_lib.wc_AesGcmEncrypt(
            byref(aes), out, plaintext, c_uint32(len(plaintext)), nonce, c_uint32(len(nonce)),
            tag, c_uint32(16), aad, c_uint32(len(aad)),
        ), "wc_AesGcmEncrypt")
        return out.raw[:len(plaintext)] + tag.raw[:16]

    def aead_decrypt(self, *, key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes = b"") -> bytes:
        ct, tag = ciphertext[:-16], ciphertext[-16:]
        aes = ctypes.create_string_buffer(512)
        _check(_lib.wc_AesGcmSetKey(byref(aes), key, c_uint32(len(key))), "wc_AesGcmSetKey")
        out = create_string_buffer(len(ct))
        _check(_lib.wc_AesGcmDecrypt(
            byref(aes), out, ct, c_uint32(len(ct)), nonce, c_uint32(len(nonce)),
            tag, c_uint32(16), aad, c_uint32(len(aad)),
        ), "wc_AesGcmDecrypt")
        return out.raw[:len(ct)]

    def hkdf(self, *, shared_secret: bytes, context: bytes, length: int = 32) -> bytes:
        WC_SHA256 = 2   # VERIFY against wolfssl/wolfcrypt/hash.h — stable enum, just confirm the value
        out = create_string_buffer(length)
        _check(_lib.wc_HKDF(
            c_int(WC_SHA256), shared_secret, c_uint32(len(shared_secret)),
            None, c_uint32(0), context, c_uint32(len(context)), out, c_uint32(length),
        ), "wc_HKDF")
        return out.raw[:length]