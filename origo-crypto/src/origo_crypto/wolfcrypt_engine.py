"""wolfCrypt-backed implementation of the Origo CryptoEngine contract.

Verified against the wolfssl-5.9.2 headers.
"""

from __future__ import annotations

import ctypes
from ctypes import (
    POINTER,
    byref,
    c_byte,
    c_int,
    c_ubyte,
    c_uint32,
    c_void_p,
    create_string_buffer,
)

from .engine import EncapsResult, KemKeypair

# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

_lib = ctypes.CDLL("libwolfssl.so")

# ---------------------------------------------------------------------------
# wolfCrypt constants
# ---------------------------------------------------------------------------

# From wolfssl/wolfcrypt/wc_mlkem.h
WC_ML_KEM_512 = 0
WC_ML_KEM_768 = 1
WC_ML_KEM_1024 = 2

# ML-KEM-1024 raw sizes.
ML_KEM_1024_PUBLIC_KEY_BYTES = 1568
ML_KEM_1024_PRIVATE_KEY_BYTES = 3168
ML_KEM_1024_CIPHERTEXT_BYTES = 1568
ML_KEM_SS_BYTES = 32

# From wolfssl/wolfcrypt/wc_mldsa.h
WC_ML_DSA_44 = 2
WC_ML_DSA_65 = 3
WC_ML_DSA_87 = 5

# ML-DSA-87 raw sizes (FIPS 204 / Dilithium5 fixed sizes).
ML_DSA_87_PUBLIC_KEY_BYTES = 2592
ML_DSA_87_PRIVATE_KEY_BYTES = 4896
ML_DSA_87_SIGNATURE_BYTES = 4627

# Digest identifier used by wc_HKDF()/wc_HmacSetKey(): this is the legacy
# hmac.h enum (MD5=0, SHA=1, SHA256=2, ...), NOT hash.h's WC_HASH_TYPE_*
# enum, which numbers SHA-256 differently. wc_HKDF() takes the hmac.h one.
WC_SHA256 = 2

# AES-256-GCM
AES_GCM_TAG_BYTES = 16
AES_GCM_NONCE_BYTES = 12    # NIST SP 800-38D recommended 96-bit IV
AES_256_KEY_BYTES = 32

# ---------------------------------------------------------------------------
# Opaque wolfCrypt struct buffer sizes
# ---------------------------------------------------------------------------
_WC_RNG_BUFFER_BYTES = 64
_AES_BUFFER_BYTES = 1024

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check(rc: int, operation: str) -> None:
    if rc != 0:
        raise RuntimeError(f"wolfCrypt {operation} failed, rc={rc}")

def _buffer(data: bytes) -> ctypes.Array[c_byte]:
    """Create a ctypes byte buffer from bytes."""
    return create_string_buffer(data, len(data))

# ---------------------------------------------------------------------------
# ctypes signatures
# ---------------------------------------------------------------------------

# ----------------------------- RNG -----------------------------------------

_lib.wc_InitRng.argtypes = [c_void_p]
_lib.wc_InitRng.restype = c_int

_lib.wc_FreeRng.argtypes = [c_void_p]
_lib.wc_FreeRng.restype = c_int

_lib.wc_RNG_GenerateBlock.argtypes = [c_void_p, c_void_p, c_uint32]
_lib.wc_RNG_GenerateBlock.restype = c_int

# ----------------------------- ML-KEM --------------------------------------

_lib.wc_MlKemKey_New.argtypes = [c_int, c_void_p, c_int]
_lib.wc_MlKemKey_New.restype = c_void_p

_lib.wc_MlKemKey_Delete.argtypes = [c_void_p, POINTER(c_void_p)]
_lib.wc_MlKemKey_Delete.restype = c_int

_lib.wc_MlKemKey_MakeKey.argtypes = [c_void_p, c_void_p]
_lib.wc_MlKemKey_MakeKey.restype = c_int

_lib.wc_MlKemKey_EncodePublicKey.argtypes = [c_void_p, c_void_p, c_uint32]
_lib.wc_MlKemKey_EncodePublicKey.restype = c_int

_lib.wc_MlKemKey_EncodePrivateKey.argtypes = [c_void_p, c_void_p, c_uint32]
_lib.wc_MlKemKey_EncodePrivateKey.restype = c_int

_lib.wc_MlKemKey_DecodePublicKey.argtypes = [c_void_p, c_void_p, c_uint32]
_lib.wc_MlKemKey_DecodePublicKey.restype = c_int

_lib.wc_MlKemKey_DecodePrivateKey.argtypes = [c_void_p, c_void_p, c_uint32]
_lib.wc_MlKemKey_DecodePrivateKey.restype = c_int

_lib.wc_MlKemKey_Encapsulate.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p]
_lib.wc_MlKemKey_Encapsulate.restype = c_int

_lib.wc_MlKemKey_Decapsulate.argtypes = [c_void_p, c_void_p, c_void_p, c_uint32]
_lib.wc_MlKemKey_Decapsulate.restype = c_int

# ----------------------------- ML-DSA --------------------------------------

_lib.wc_MlDsaKey_New.argtypes = [c_void_p, c_int]
_lib.wc_MlDsaKey_New.restype = c_void_p

_lib.wc_MlDsaKey_Delete.argtypes = [c_void_p, POINTER(c_void_p)]
_lib.wc_MlDsaKey_Delete.restype = c_int

_lib.wc_MlDsaKey_SetParams.argtypes = [c_void_p, c_ubyte]
_lib.wc_MlDsaKey_SetParams.restype = c_int

_lib.wc_MlDsaKey_MakeKey.argtypes = [c_void_p, c_void_p]
_lib.wc_MlDsaKey_MakeKey.restype = c_int

_lib.wc_MlDsaKey_GetPrivLen.argtypes = [c_void_p, POINTER(c_int)]
_lib.wc_MlDsaKey_GetPrivLen.restype = c_int

_lib.wc_MlDsaKey_GetPubLen.argtypes = [c_void_p, POINTER(c_int)]
_lib.wc_MlDsaKey_GetPubLen.restype = c_int

_lib.wc_MlDsaKey_GetSigLen.argtypes = [c_void_p, POINTER(c_int)]
_lib.wc_MlDsaKey_GetSigLen.restype = c_int

_lib.wc_MlDsaKey_ExportPubRaw.argtypes = [c_void_p, c_void_p, POINTER(c_uint32)]
_lib.wc_MlDsaKey_ExportPubRaw.restype = c_int

_lib.wc_MlDsaKey_ExportPrivRaw.argtypes = [c_void_p, c_void_p, POINTER(c_uint32)]
_lib.wc_MlDsaKey_ExportPrivRaw.restype = c_int

_lib.wc_MlDsaKey_ImportPubRaw.argtypes = [c_void_p, c_void_p, c_uint32]
_lib.wc_MlDsaKey_ImportPubRaw.restype = c_int

_lib.wc_MlDsaKey_ImportPrivRaw.argtypes = [c_void_p, c_void_p, c_uint32]
_lib.wc_MlDsaKey_ImportPrivRaw.restype = c_int

_lib.wc_MlDsaKey_SignCtx.argtypes = [
    c_void_p,           # key
    c_void_p,           # ctx
    c_ubyte,            # ctxLen
    c_void_p,           # sig
    POINTER(c_uint32),  # sigLen
    c_void_p,           # msg
    c_uint32,           # msgLen
    c_void_p,           # rng
]
_lib.wc_MlDsaKey_SignCtx.restype = c_int

_lib.wc_MlDsaKey_VerifyCtx.argtypes = [
    c_void_p,           # key
    c_void_p,           # sig
    c_uint32,           # sigLen
    c_void_p,           # ctx
    c_ubyte,            # ctxLen
    c_void_p,           # msg
    c_uint32,           # msgLen
    POINTER(c_int),     # res
]
_lib.wc_MlDsaKey_VerifyCtx.restype = c_int

# ----------------------------- AES-256-GCM ----------------------------------
# The build exports the one-shot AesGcmEncrypt/AesGcmDecrypt API.

_lib.wc_AesGcmSetKey.argtypes = [c_void_p, c_void_p, c_uint32]
_lib.wc_AesGcmSetKey.restype = c_int

_lib.wc_AesGcmEncrypt.argtypes = [
    c_void_p,           # aes
    c_void_p,           # out
    c_void_p,           # in
    c_uint32,           # sz
    c_void_p,           # iv
    c_uint32,           # ivSz
    c_void_p,           # authTag
    c_uint32,           # authTagSz
    c_void_p,           # authIn
    c_uint32,           # authInSz
]
_lib.wc_AesGcmEncrypt.restype = c_int

_lib.wc_AesGcmDecrypt.argtypes = [
    c_void_p, c_void_p, c_void_p, c_uint32,
    c_void_p, c_uint32,
    c_void_p, c_uint32,
    c_void_p, c_uint32,
]
_lib.wc_AesGcmDecrypt.restype = c_int

try:
    _lib.wc_AesInit.argtypes = [c_void_p, c_void_p, c_int]
    _lib.wc_AesInit.restype = c_int
    _HAVE_AES_INIT = True
except AttributeError:
    _HAVE_AES_INIT = False

try:
    _lib.wc_AesFree.argtypes = [c_void_p]
    _lib.wc_AesFree.restype = None
    _HAVE_AES_FREE = True
except AttributeError:
    _HAVE_AES_FREE = False

# ----------------------------- HKDF -----------------------------------------

_lib.wc_HKDF.argtypes = [
    c_int,               # type
    c_void_p, c_uint32,  # inKey, inKeySz
    c_void_p, c_uint32,  # salt, saltSz
    c_void_p, c_uint32,  # info, infoSz
    c_void_p, c_uint32,  # out, outSz
]
_lib.wc_HKDF.restype = c_int

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class WolfCryptEngine:

    def __init__(self) -> None:
        # WC_RNG is an opaque wolfCrypt structure.
        self._rng = create_string_buffer(_WC_RNG_BUFFER_BYTES)
        _check(_lib.wc_InitRng(byref(self._rng)), "wc_InitRng")

    def close(self) -> None:
        """Release the underlying WC_RNG. Safe to call more than once."""
        rng = getattr(self, "_rng", None)
        if rng is not None:
            _lib.wc_FreeRng(byref(rng))
            self._rng = None

    def __enter__(self) -> "WolfCryptEngine":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # RNG
    # ------------------------------------------------------------------

    def random_bytes(self, n: int) -> bytes:
        if n < 0:
            raise ValueError("n must be non-negative")
        if n == 0:
            return b""
        buf = create_string_buffer(n)
        _check(
            _lib.wc_RNG_GenerateBlock(byref(self._rng), buf, c_uint32(n)),
            "wc_RNG_GenerateBlock",
        )
        return bytes(buf.raw[:n])

    # ------------------------------------------------------------------
    # ML-KEM-1024
    # ------------------------------------------------------------------

    def kem_keygen(self) -> KemKeypair:
        key = _lib.wc_MlKemKey_New(WC_ML_KEM_1024, None, -2)
        if not key:
            raise RuntimeError("wc_MlKemKey_New failed")
        try:
            _check(_lib.wc_MlKemKey_MakeKey(key, byref(self._rng)), "wc_MlKemKey_MakeKey")
            ek = create_string_buffer(ML_KEM_1024_PUBLIC_KEY_BYTES)
            dk = create_string_buffer(ML_KEM_1024_PRIVATE_KEY_BYTES)
            _check(
                _lib.wc_MlKemKey_EncodePublicKey(key, ek, c_uint32(ML_KEM_1024_PUBLIC_KEY_BYTES)),
                "wc_MlKemKey_EncodePublicKey",
            )
            _check(
                _lib.wc_MlKemKey_EncodePrivateKey(key, dk, c_uint32(ML_KEM_1024_PRIVATE_KEY_BYTES)),
                "wc_MlKemKey_EncodePrivateKey",
            )
            return KemKeypair(
                ek=bytes(ek.raw[:ML_KEM_1024_PUBLIC_KEY_BYTES]),
                dk=bytes(dk.raw[:ML_KEM_1024_PRIVATE_KEY_BYTES]),
            )
        finally:
            key_ptr = c_void_p(key)
            _check(_lib.wc_MlKemKey_Delete(key_ptr, byref(key_ptr)), "wc_MlKemKey_Delete")

    def kem_encapsulate(self, ek: bytes) -> EncapsResult:
        if len(ek) != ML_KEM_1024_PUBLIC_KEY_BYTES:
            raise ValueError(
                f"ML-KEM-1024 public key must be {ML_KEM_1024_PUBLIC_KEY_BYTES} bytes, got {len(ek)}"
            )
        key = _lib.wc_MlKemKey_New(WC_ML_KEM_1024, None, -2)
        if not key:
            raise RuntimeError("wc_MlKemKey_New failed")
        try:
            ek_buf = _buffer(ek)
            _check(
                _lib.wc_MlKemKey_DecodePublicKey(key, ek_buf, c_uint32(len(ek))),
                "wc_MlKemKey_DecodePublicKey",
            )
            ciphertext = create_string_buffer(ML_KEM_1024_CIPHERTEXT_BYTES)
            shared_secret = create_string_buffer(ML_KEM_SS_BYTES)
            _check(
                _lib.wc_MlKemKey_Encapsulate(key, ciphertext, shared_secret, byref(self._rng)),
                "wc_MlKemKey_Encapsulate",
            )
            return EncapsResult(
                ciphertext=bytes(ciphertext.raw[:ML_KEM_1024_CIPHERTEXT_BYTES]),
                shared_secret=bytes(shared_secret.raw[:ML_KEM_SS_BYTES]),
            )
        finally:
            key_ptr = c_void_p(key)
            _check(_lib.wc_MlKemKey_Delete(key_ptr, byref(key_ptr)), "wc_MlKemKey_Delete")

    def kem_decapsulate(self, dk: bytes, ciphertext: bytes) -> bytes:
        if len(dk) != ML_KEM_1024_PRIVATE_KEY_BYTES:
            raise ValueError(
                f"ML-KEM-1024 private key must be {ML_KEM_1024_PRIVATE_KEY_BYTES} bytes, got {len(dk)}"
            )
        if len(ciphertext) != ML_KEM_1024_CIPHERTEXT_BYTES:
            raise ValueError(
                f"ML-KEM-1024 ciphertext must be {ML_KEM_1024_CIPHERTEXT_BYTES} bytes, got {len(ciphertext)}"
            )
        key = _lib.wc_MlKemKey_New(WC_ML_KEM_1024, None, -2)
        if not key:
            raise RuntimeError("wc_MlKemKey_New failed")
        try:
            dk_buf = _buffer(dk)
            ct_buf = _buffer(ciphertext)
            _check(
                _lib.wc_MlKemKey_DecodePrivateKey(key, dk_buf, c_uint32(len(dk))),
                "wc_MlKemKey_DecodePrivateKey",
            )
            shared_secret = create_string_buffer(ML_KEM_SS_BYTES)
            _check(
                _lib.wc_MlKemKey_Decapsulate(key, shared_secret, ct_buf, c_uint32(len(ciphertext))),
                "wc_MlKemKey_Decapsulate",
            )
            return bytes(shared_secret.raw[:ML_KEM_SS_BYTES])
        finally:
            key_ptr = c_void_p(key)
            _check(_lib.wc_MlKemKey_Delete(key_ptr, byref(key_ptr)), "wc_MlKemKey_Delete")

    # ------------------------------------------------------------------
    # ML-DSA-87
    # ------------------------------------------------------------------

    def _new_mldsa_key(self) -> c_void_p:
        key = _lib.wc_MlDsaKey_New(None, -2)
        if not key:
            raise RuntimeError("wc_MlDsaKey_New failed")
        _check(_lib.wc_MlDsaKey_SetParams(key, c_ubyte(WC_ML_DSA_87)), "wc_MlDsaKey_SetParams")
        return key

    def _delete_mldsa_key(self, key) -> None:
        key_ptr = c_void_p(key)
        _check(_lib.wc_MlDsaKey_Delete(key_ptr, byref(key_ptr)), "wc_MlDsaKey_Delete")

    def dsa_keygen(self) -> tuple[bytes, bytes]:
        key = self._new_mldsa_key()
        try:
            _check(_lib.wc_MlDsaKey_MakeKey(key, byref(self._rng)), "wc_MlDsaKey_MakeKey")

            pub_len = c_int(0)
            priv_len = c_int(0)
            _check(_lib.wc_MlDsaKey_GetPubLen(key, byref(pub_len)), "wc_MlDsaKey_GetPubLen")
            _check(_lib.wc_MlDsaKey_GetPrivLen(key, byref(priv_len)), "wc_MlDsaKey_GetPrivLen")

            pub = create_string_buffer(pub_len.value)
            priv = create_string_buffer(priv_len.value)
            pub_out_len = c_uint32(pub_len.value)
            priv_out_len = c_uint32(priv_len.value)

            _check(
                _lib.wc_MlDsaKey_ExportPubRaw(key, pub, byref(pub_out_len)),
                "wc_MlDsaKey_ExportPubRaw",
            )
            _check(
                _lib.wc_MlDsaKey_ExportPrivRaw(key, priv, byref(priv_out_len)),
                "wc_MlDsaKey_ExportPrivRaw",
            )

            return (
                bytes(pub.raw[:pub_out_len.value]),
                bytes(priv.raw[:priv_out_len.value]),
            )
        finally:
            self._delete_mldsa_key(key)

    def dsa_sign(self, *, private_key: bytes, message: bytes) -> bytes:
        key = self._new_mldsa_key()
        try:
            priv_buf = _buffer(private_key)
            msg_buf = _buffer(message)

            _check(
                _lib.wc_MlDsaKey_ImportPrivRaw(key, priv_buf, c_uint32(len(private_key))),
                "wc_MlDsaKey_ImportPrivRaw",
            )

            sig_len = c_int(0)
            _check(_lib.wc_MlDsaKey_GetSigLen(key, byref(sig_len)), "wc_MlDsaKey_GetSigLen")

            sig = create_string_buffer(sig_len.value)
            actual_sig_len = c_uint32(sig_len.value)

            # ctx=NULL, ctxLen=0 -> plain FIPS 204 ML-DSA.Sign (empty context).
            _check(
                _lib.wc_MlDsaKey_SignCtx(
                    key,
                    None, 0,
                    sig, byref(actual_sig_len),
                    msg_buf, c_uint32(len(message)),
                    byref(self._rng),
                ),
                "wc_MlDsaKey_SignCtx",
            )
            return bytes(sig.raw[:actual_sig_len.value])
        finally:
            self._delete_mldsa_key(key)

    def dsa_verify(self, *, public_key: bytes, message: bytes, signature: bytes) -> bool:
        key = self._new_mldsa_key()
        try:
            pub_buf = _buffer(public_key)
            msg_buf = _buffer(message)
            sig_buf = _buffer(signature)

            _check(
                _lib.wc_MlDsaKey_ImportPubRaw(key, pub_buf, c_uint32(len(public_key))),
                "wc_MlDsaKey_ImportPubRaw",
            )

            result = c_int(0)
            rc = _lib.wc_MlDsaKey_VerifyCtx(
                key,
                sig_buf, c_uint32(len(signature)),
                None, 0,
                msg_buf, c_uint32(len(message)),
                byref(result),
            )
            return rc == 0 and result.value == 1
        finally:
            self._delete_mldsa_key(key)

    # ------------------------------------------------------------------
    # AES-256-GCM
    # ------------------------------------------------------------------

    def aead_encrypt(
        self,
        *,
        key: bytes,
        nonce: bytes,
        plaintext: bytes,
        aad: bytes = b"",
    ) -> bytes:
        if len(key) != AES_256_KEY_BYTES:
            raise ValueError(f"AES-256-GCM key must be {AES_256_KEY_BYTES} bytes, got {len(key)}")
        if len(nonce) != AES_GCM_NONCE_BYTES:
            raise ValueError(f"AES-GCM nonce must be {AES_GCM_NONCE_BYTES} bytes, got {len(nonce)}")

        aes = create_string_buffer(_AES_BUFFER_BYTES)
        try:
            if _HAVE_AES_INIT:
                _check(_lib.wc_AesInit(aes, None, -2), "wc_AesInit")
            _check(_lib.wc_AesGcmSetKey(aes, _buffer(key), c_uint32(len(key))), "wc_AesGcmSetKey")

            out = create_string_buffer(max(len(plaintext), 1))
            tag = create_string_buffer(AES_GCM_TAG_BYTES)
            pt_buf = _buffer(plaintext) if plaintext else None
            aad_buf = _buffer(aad) if aad else None

            _check(
                _lib.wc_AesGcmEncrypt(
                    aes,
                    out,
                    pt_buf,
                    c_uint32(len(plaintext)),
                    _buffer(nonce),
                    c_uint32(len(nonce)),
                    tag,
                    c_uint32(AES_GCM_TAG_BYTES),
                    aad_buf,
                    c_uint32(len(aad)),
                ),
                "wc_AesGcmEncrypt",
            )
            # ciphertext||tag, since the contract has no separate tag field.
            return bytes(out.raw[:len(plaintext)]) + bytes(tag.raw[:AES_GCM_TAG_BYTES])
        finally:
            if _HAVE_AES_FREE:
                _lib.wc_AesFree(aes)

    def aead_decrypt(
        self,
        *,
        key: bytes,
        nonce: bytes,
        ciphertext: bytes,
        aad: bytes = b"",
    ) -> bytes:
        if len(key) != AES_256_KEY_BYTES:
            raise ValueError(f"AES-256-GCM key must be {AES_256_KEY_BYTES} bytes, got {len(key)}")
        if len(nonce) != AES_GCM_NONCE_BYTES:
            raise ValueError(f"AES-GCM nonce must be {AES_GCM_NONCE_BYTES} bytes, got {len(nonce)}")
        if len(ciphertext) < AES_GCM_TAG_BYTES:
            raise ValueError("ciphertext shorter than the AES-GCM tag; not a valid ciphertext")

        body = ciphertext[:-AES_GCM_TAG_BYTES]
        tag = ciphertext[-AES_GCM_TAG_BYTES:]

        aes = create_string_buffer(_AES_BUFFER_BYTES)
        try:
            if _HAVE_AES_INIT:
                _check(_lib.wc_AesInit(aes, None, -2), "wc_AesInit")
            _check(_lib.wc_AesGcmSetKey(aes, _buffer(key), c_uint32(len(key))), "wc_AesGcmSetKey")

            out = create_string_buffer(max(len(body), 1))
            body_buf = _buffer(body) if body else None
            aad_buf = _buffer(aad) if aad else None

            # Non-zero rc means either a plain error or a failed auth-tag
            # check (tampered ciphertext/aad/tag) -- both abort the same
            # way here, consistent with every other call in this file.
            _check(
                _lib.wc_AesGcmDecrypt(
                    aes,
                    out,
                    body_buf,
                    c_uint32(len(body)),
                    _buffer(nonce),
                    c_uint32(len(nonce)),
                    _buffer(tag),
                    c_uint32(AES_GCM_TAG_BYTES),
                    aad_buf,
                    c_uint32(len(aad)),
                ),
                "wc_AesGcmDecrypt",
            )
            return bytes(out.raw[:len(body)])
        finally:
            if _HAVE_AES_FREE:
                _lib.wc_AesFree(aes)

    # ------------------------------------------------------------------
    # HKDF
    # ------------------------------------------------------------------

    def hkdf(self, *, shared_secret: bytes, context: bytes, length: int = 32) -> bytes:
        if length <= 0:
            raise ValueError("length must be positive")

        out = create_string_buffer(length)
        ss_buf = _buffer(shared_secret) if shared_secret else None
        ctx_buf = _buffer(context) if context else None

        _check(
            _lib.wc_HKDF(
                WC_SHA256,
                ss_buf, c_uint32(len(shared_secret)),
                None, 0,                       # no salt
                ctx_buf, c_uint32(len(context)),
                out, c_uint32(length),
            ),
            "wc_HKDF",
        )
        return bytes(out.raw[:length])