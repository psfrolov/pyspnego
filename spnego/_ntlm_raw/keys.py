# Copyright: (c) 2020, Jordan Borean (@jborean93) <jborean93@gmail.com>
# MIT License (see LICENSE or https://opensource.org/licenses/MIT)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import hashlib
import hmac
import io

from cryptography.hazmat.primitives.ciphers import (
    algorithms,
    Cipher,
)

from cryptography.hazmat.backends import (
    default_backend,
)

from typing import (
    Optional,
    Tuple,
)

from spnego._ntlm_raw.des import (
    DES,
)

from spnego._ntlm_raw.messages import (
    FileTime,
    NegotiateFlags,
    TargetInfo,
)

from spnego._text import (
    text_type,
    to_bytes,
)


def des(k, d):  # type: (bytes, bytes) -> bytes
    """DES encryption.

    Indicates the encryption of an 8-byte data item `d` with the 7-byte key `k` using the Data Encryption Standard
    (DES) algorithm in Electronic Codebook (ECB) mode. The result is 8 bytes in length ([FIPS46-2]).

    Args:
        k: The 7-byte key to use in the DES cipher.
        d: The 8-byte data block to encrypt.

    Returns:
        bytes: The encrypted data block.
    """
    return DES(DES.key56_to_key64(k)).encrypt(d)


def desl(k, d):  # type: (bytes, bytes) -> bytes
    """Encryption using the DES Long algorithm.

    Indicates the encryption of an 8-byte data item `d` with the 16-byte key `k` using the Data Encryption
    Standard Long (DESL) algorithm. The result is 24 bytes in length.

    `DESL(K, D)` as by MS-NLMP `DESL`_ is computed as follows::

        ConcatenationOf(
            DES(K[0..6], D),
            DES(K[7..13], D),
            DES(ConcatenationOf(K[14..15], Z(5)), D),
        );

    Args:
        k: The key to use for the DES cipher, will be truncated to 16 bytes and then padded to 21 bytes.
        d: The value to run through the DESL algorithm, will be truncated to 8 bytes.

    Returns:
        bytes: The output of the DESL algorithm.

    .. _DESL:
        https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-nlmp/26c42637-9549-46ae-be2e-90f6f1360193
    """
    k = k[:16].ljust(21, b"\x00")  # Key needs to be stripped at 16 characters and then padded to 21 chars.
    d = d[:8].ljust(8, b"\x00")  # Data need to be at most 8 bytes long.

    b_value = io.BytesIO()

    b_value.write(des(k[:7], d))
    b_value.write(des(k[7:14], d))
    b_value.write(des(k[14:], d))

    return b_value.getvalue()


def hmac_md5(key, data):
    """ Simple wrapper function for a HMAC MD5 digest. """
    return hmac.new(key, data, digestmod=hashlib.md5).digest()


def rc4k(k, d):  # type: (bytes, bytes) -> bytes
    """RC4 encryption with an explicit key.

    Indicates the encryption of data item `d` with the key `k` using the `RC4`_ algorithm.

    Args:
        k: The key to use for the RC4 cipher.
        d: The data to encrypt.

    Returns:
        bytes: The RC4 encrypted bytes.

    .. _RC4K:
        https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-nlmp/26c42637-9549-46ae-be2e-90f6f1360193
    """
    arc4 = algorithms.ARC4(k)
    cipher = Cipher(arc4, mode=None, backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(d)


def lmowfv1(password):  # type: (text_type) -> bytes
    """NTLMv1 LMOWFv1 function

    The Lan Manager v1 one way function as documented under `NTLM v1 Authentication`_.

    The pseudo-code for this function is::

        Define LMOWFv1(Passwd, User, UserDom) as
            ConcatenationOf(
                DES(UpperCase(Passwd)[0..6], "KGS!@#$%"),
                DES(UpperCase(Passwd)[7..13], "KGS!@#$%"),
            );

    Args:
        password: The password for the user.

    Returns:
        bytes: The LMv1 one way hash of the user's password.

    .. _NTLM v1 Authentication:
        https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-nlmp/464551a8-9fc4-428e-b3d3-bc5bfb2e73a5
    """
    # Fix the password to upper case and pad the length to exactly 14 bytes.
    b_password = to_bytes(password.upper()).ljust(14, b"\x00")[:14]

    b_hash = io.BytesIO()
    for start, end in [(0, 7), (7, 14)]:
        b_hash.write(des(b_password[start:end], b'KGS!@#$%'))

    return b_hash.getvalue()


def ntowfv1(password):  # type: (text_type) -> bytes
    """NTLMv1 NTOWFv1 function

    The NT v1 one way function as documented under `NTLM v1 Authentication`_.

    The pseudo-code for this function is::

        Define NTOWFv1(Passwd, User, UserDom) as MD4(UNICODE(Passwd))

    Args:
        password: The password for the user.

    Returns:
        bytes: The NTv1 one way hash of the user's password.

    .. _NTLM v1 Authentication:
        https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-nlmp/464551a8-9fc4-428e-b3d3-bc5bfb2e73a5
    """
    return hashlib.new('md4', to_bytes(password, encoding='utf-16-le')).digest()


def ntowfv2(username, password, domain_name):  # type: (text_type, text_type, Optional[text_type]) -> bytes
    """NTLMv2 NTOWFv2 function

    The NT v2 one way function as documented under `NTLM v2 Authentication`_.

    The pseudo-code for this function is::

        Define NTOWFv2(Passwd, User, UserDom) as

            HMAC_MD5(MD4(UNICODE(Passwd)), UNICODE(ConcatenationOf(Uppercase(User), UserDom)))

    Args:

    Returns:
        bytes: The NTv2 one way has of the user's credentials.

    .. _NTLM v2 Authentication:
        https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-nlmp/5e550938-91d4-459f-b67d-75d70009e3f3
    """
    digest = ntowfv1(password)  # ntowfv1 creates the MD4 hash of the user's password.
    b_user = to_bytes(username.upper() + (domain_name or u""), encoding='utf-16-le')
    return hmac_md5(digest, b_user)


def compute_response_v1(flags, response_key_nt, response_key_lm, server_challenge, client_challenge,
                        no_lm_response=True):
    # type: (NegotiateFlags, bytes, bytes, bytes, bytes, bool) -> Tuple[bytes, bytes, bytes]
    """Compute NT and LM Response for NTLMv1.

    Computes the NT and LM Response for NTLMv1 messages. The response is dependent on the flags that were negotiated
    between the client and server.  The anonymous auth is handled by the caller.

    The pseudo-code for this function as documented under `NTLM v1 Authentication`_ is::

        Define ComputeResponse(NegFlg, ResponseKeyNT, ResponseKeyLM, CHALLENGE_MESSAGE.ServerChallenge,
            ClientChallenge, Time, ServerName) As

            If (User is set to "" AND Passwd is set to "")
                -- Special case for anonymous authentication
                Set NtChallengeResponseLen to 0
                Set NtChallengeResponseMaxLen to 0
                Set NtChallengeResponseBufferOffset to 0

                Set LmChallengeResponse to Z(1)
            ElseIf
                If (NTLMSSP_NEGOTIATE_EXTENDED_SESSIONSECURITY flag is set in NegFlg)
                    Set NtChallengeResponse to DESL(ResponseKeyNT,
                        MD5(ConcatenationOf(CHALLENGE_MESSAGE.ServerChallenge, ClientChallenge))[0..7])

                    Set LmChallengeResponse to ConcatenationOf{ClientChallenge, Z(16)}
                Else
                    Set NtChallengeResponse to DESL(ResponseKeyNT, CHALLENGE_MESSAGE.ServerChallenge)

                    If (NoLMResponseNTLMv1 is TRUE)
                        Set LmChallengeResponse to NtChallengeResponse
                    Else
                        Set LmChallengeResponse to DESL(ResponseKeyLM, CHALLENGE_MESSAGE.ServerChallenge)
                    EndIf
                EndIf
            EndIf

        Set SessionBaseKey to MD4(NTOWF)

    Args:
        flags: The negotiated flags between the initiator and acceptor.
        response_key_nt: The response key computed by :meth:`ntowfv1`.
        response_key_lm: The response key computed by :meth:`lmowfv1`.
        server_challenge: The 8 byte nonce generated by the acceptor.
        client_challenge: The 8 byte nonce generated by the initiator.
        no_lm_response: Whether to compute (True) the `LmChallengeResponse` or not (False) when extended session
            security was not negotiated.

    Returns:
        Tuple[bytes, bytes, bytes]: Returns the NTChallengeResponse, LMChallengeResponse and KeyExchangeKey.

    .. _NTLM v1 Authentication:
        https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-nlmp/464551a8-9fc4-428e-b3d3-bc5bfb2e73a5
    """
    if flags & NegotiateFlags.extended_session_security:
        nt_response = desl(response_key_nt, hashlib.md5(server_challenge + client_challenge[:8]).digest())
        lm_response = client_challenge + (b"\x00" * 16)

    else:
        nt_response = lm_response = desl(response_key_nt, server_challenge)

        if not no_lm_response:
            lm_response = desl(response_key_lm, server_challenge)

    session_base_key = hashlib.new('md4', response_key_nt).digest()
    key_exchange_key = kxkey(flags, session_base_key, response_key_lm, lm_response, server_challenge)

    return nt_response, lm_response, key_exchange_key


def compute_response_v2(response_key_nt, server_challenge, client_challenge, time, av_pairs):
    # type: (bytes, bytes, bytes, FileTime, TargetInfo) -> Tuple[bytes, bytes, bytes]
    """Compute NT and LM Response for NTLMv2.

    Computes the NT and LM Response for NTLMv2 messages. The response is dependent on the flags that were negotiated
    between the client and server. The anonymous auth is handled by the caller.

    The pseudo-code for this function as documented under `NTLM v2 Authentication`_ is::

        Define ComputeResponse(NegFlg, ResponseKeyNT, ResponseKeyLM, CHALLENGE_MESSAGE.ServerChallenge,
            ClientChallenge, Time, ServerName) As

            If (User is set to "" && Passwd is set to "")
                -- Special case for anonymous authentication
                Set NtChallengeResponseLen to 0
                Set NtChallengeResponseMaxLen to 0
                Set NtChallengeResponseBufferOffset to 0

                Set LmChallengeResponse to Z(1)
            Else
                Set temp to ConcatenationOf(Responserversion, HiResponserversion, Z(6), Time, ClientChallenge, Z(4),
                    ServerName, Z(4))

                Set NTProofStr to HMAC_MD5(ResponseKeyNT, ConcatenationOf(CHALLENGE_MESSAGE.ServerChallenge,temp))

                Set NtChallengeResponse to ConcatenationOf(NTProofStr, temp)

                Set LmChallengeResponse to ConcatenationOf(
                    HMAC_MD5(ResponseKeyLM, ConcatenationOf(CHALLENGE_MESSAGE.ServerChallenge, ClientChallenge)),
                    ClientChallenge)
            EndIf

        Set SessionBaseKey to HMAC_MD5(ResponseKeyNT, NTProofStr)

    Args:
        response_key_nt: The response key computed by :meth:`ntwofv2`. The `ResponseKeyLM` is the same value so we only
            pass in the 1 key.
        server_challenge: The 8 byte nonce generated by the acceptor.
        client_challenge: The 8 byte nonce generated by the initiator.
        time: The FileTime to place in the NT hash.
        av_pairs: The TargetInfo AvPairs fields that are placed in the Authenticate message.

    Returns:
        Tuple[bytes, bytes, bytes]: Returns the NTChallengeResponse, LMChallengeResponse and KeyExchangeKey.

    .. _NTLM v2 Authentication:
        https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-nlmp/5e550938-91d4-459f-b67d-75d70009e3f3
    """
    temp = b"\x01\x01\x00\x00\x00\x00\x00\x00" + time.pack() + client_challenge + b"\x00\x00\x00\x00" + \
           av_pairs.pack() + b"\x00\x00\x00\x00"
    nt_proof_str = hmac_md5(response_key_nt, server_challenge + temp)

    nt_response = nt_proof_str + temp
    lm_response = hmac_md5(response_key_nt, server_challenge + client_challenge) + client_challenge
    session_base_key = hmac_md5(response_key_nt, nt_proof_str)

    return nt_response, lm_response, session_base_key  # Is KeyExchangeKey in NTLMv2.


def kxkey(flags, session_base_key, lmowf, lm_response, server_challenge):
    # type: (NegotiateFlags, bytes, bytes, bytes, bytes) -> bytes
    """NTLM KXKEY function.

    The MS-NLMP `KXKEY`_ function used to derive the key exchange key for a security context. This is only for NTLMv1
    contexts as NTLMv2 just re-uses the session base key.

    Args:
        flags: The negotiate flags in the Challenge msg.
        session_base_key: The session base key from :meth:`compute_response_v1`.
        lmowf: The LM hash from :meth:`lmowfv1`.
        lm_response: The lm response from :meth:`compute_response_v1`.
        server_challenge: The server challenge in the Challenge msg.

    Returns:
        bytes: The derived key exchange key.

    .. _KXKEY:
        https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-nlmp/d86303b5-b29e-4fb9-b119-77579c761370
    """
    if flags & NegotiateFlags.extended_session_security:
        return hmac_md5(session_base_key, server_challenge + lm_response[:8])

    elif flags & NegotiateFlags.lm_key:
        b_data = lm_response[:8]
        return des(lmowf[:7], b_data) + des(lmowf[7:8] + b"\xbd\xbd\xbd\xbd\xbd\xbd", b_data)

    elif flags & NegotiateFlags.non_nt_session_key:
        return lmowf[:8] + b"\x00" * 8

    else:
        return session_base_key


def signkey(flags, session_key, usage):
    # type: (NegotiateFlags, bytes, str) -> Optional[bytes]
    """NTLM SIGNKEY function.

    The MS-NLMP `SIGNKEY`_ function used to generate the signing keys for a security context.

    The pseudo-code for this function as documented under `SIGNKEY`_ is::

        Define SIGNKEY(NegFlg, ExportedSessionKey, Mode) as

            If (NTLMSSP_NEGOTIATE_EXTENDED_SESSIONSECURITY flag is set in NegFlg)
                If (Mode equals "Client")
                    Set SignKey to MD5(ConcatenationOf(ExportedSessionKey,
                        "session key to client-to-server signing key magic constant"))

                Else
                    Set SignKey to MD5(ConcatenationOf(ExportedSessionKey,
                        "session key to server-to-client signing key magic constant"))

                Endif
            Else
                Set  SignKey to NIL

            Endif
        EndDefine

    Args:
        flags: The negotiated flags between the initiator and acceptor.
        session_key: The derived session key.
        usage: Whether the signing key is for the 'initiate' or 'accept' context.

    Returns:
        bytes: The derived singing key.

    .. _SIGNKEY:
        https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-nlmp/524cdccb-563e-4793-92b0-7bc321fce096
    """
    if flags & NegotiateFlags.extended_session_security == 0:
        return

    direction = b"client-to-server" if usage == 'initiate' else b"server-to-client"

    return hashlib.md5(session_key + b"session key to %s signing key magic constant\x00" % direction).digest()


def sealkey(flags, session_key, usage):
    # type: (NegotiateFlags, bytes, str) -> bytes
    """NTLM SEALKEY function.

    The MS-NLMP `SEALKEY`_ function used to generate the sealing keys for a security context.

    The pseudo-code for this function as documented under `SEALKEY`_ is::

        Define SEALKEY(NegFlg, ExportedSessionKey, Mode) as

            If (NTLMSSP_NEGOTIATE_EXTENDED_SESSIONSECURITY flag is set in NegFlg)

                If ( NTLMSSP_NEGOTIATE_128 is set in NegFlg)
                    Set SealKey to ExportedSessionKey

                ElseIf ( NTLMSSP_NEGOTIATE_56 flag is set in NegFlg)
                    Set SealKey to ExportedSessionKey[0..6]

                Else
                    Set SealKey to ExportedSessionKey[0..4]

                Endif

                If (Mode equals "Client")
                    Set SealKey to MD5(ConcatenationOf(SealKey,
                        "session key to client-to-server sealing key magic constant"))

                Else
                    Set SealKey to MD5(ConcatenationOf(SealKey,
                        "session key to server-to-client sealing key magic constant"))

                Endif
            ElseIf ((NTLMSSP_NEGOTIATE_LM_KEY is set in NegFlg) or ((NTLMSSP_NEGOTIATE_DATAGRAM is set in NegFlg) and
                                                                    (NTLMRevisionCurrent >= NTLMSSP_REVISION_W2K3)))

                If (NTLMSSP_NEGOTIATE_56 flag is set in NegFlg)
                    Set SealKey to ConcatenationOf(ExportedSessionKey[0..6], 0xA0)

                Else
                    Set SealKey to ConcatenationOf(ExportedSessionKey[0..4], 0xE5, 0x38, 0xB0)

                EndIf

            Else
                Set SealKey to ExportedSessionKey
            Endif
        EndDefine

    Args:
        flags: The negotiated flags between the initiator and acceptor.
        session_key: The derived session key.
        usage: Whether the sealing key is for the 'initiate' or 'accept' context.

    Returns:
        bytes: The derived sealing key.

    .. _SEALKEY:
        https://docs.microsoft.com/en-us/openspecs/windows_protocols/ms-nlmp/bf39181d-e95d-40d7-a740-ab4ec3dc363d
    """
    if flags & NegotiateFlags.extended_session_security:
        if flags & NegotiateFlags.key_128:
            seal_key = session_key

        elif flags & NegotiateFlags.key_56:
            seal_key = session_key[:7]

        else:
            seal_key = session_key[:5]

        direction = b"client-to-server" if usage == 'initiate' else b"server-to-client"

        return hashlib.md5(seal_key + b"session key to %s sealing key magic constant\x00" % direction).digest()

    elif flags & NegotiateFlags.lm_key or flags & NegotiateFlags.datagram:
        if flags & NegotiateFlags.key_56:
            return session_key[:7] + b"\xA0"

        else:
            return session_key[:5] + b"\xE5\x38\xB0"

    else:
        return session_key
