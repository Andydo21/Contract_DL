/* Password protection of the signing private key, done in the browser.
 *
 * The key file is a standard encrypted PKCS#8 PEM ("ENCRYPTED PRIVATE KEY": PBES2 with PBKDF2-HMAC-SHA256 and
 * AES-256-CBC), so OpenSSL and other tools read it with the same password. A key file saved before this protection
 * existed ("PRIVATE KEY") is still accepted.
 */
(function (root) {
    const subtle = (root.crypto || require('crypto').webcrypto).subtle;
    const random = size => (root.crypto || require('crypto').webcrypto).getRandomValues(new Uint8Array(size));
    const ITERATIONS = 600000;
    const OID = {
        pbes2: [0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x05, 0x0d],
        pbkdf2: [0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x05, 0x0c],
        hmacSha1: [0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x02, 0x07],
        hmacSha256: [0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x02, 0x09],
        hmacSha512: [0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x02, 0x0b],
        aes128: [0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x01, 0x02],
        aes256: [0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x01, 0x2a],
    };
    const same = (a, b) => a.length === b.length && a.every((value, i) => value === b[i]);

    function join(parts) {
        const out = new Uint8Array(parts.reduce((size, part) => size + part.length, 0));
        let offset = 0;
        for (const part of parts) { out.set(part, offset); offset += part.length; }
        return out;
    }

    // One DER element: tag, length, content.
    function der(tag, ...parts) {
        const body = join(parts.map(part => part instanceof Uint8Array ? part : new Uint8Array(part)));
        let length = [body.length];
        if (body.length > 127) {
            length = [];
            for (let rest = body.length; rest > 0; rest = Math.floor(rest / 256)) length.unshift(rest % 256);
            length.unshift(0x80 | length.length);
        }
        return join([new Uint8Array([tag, ...length]), body]);
    }

    function integer(value) {
        const digits = [];
        for (let rest = value; rest > 0; rest = Math.floor(rest / 256)) digits.unshift(rest % 256);
        if (!digits.length || digits[0] & 0x80) digits.unshift(0);
        return der(0x02, digits);
    }

    // The elements directly inside `data`, as {tag, value}.
    function elements(data) {
        const out = [];
        let offset = 0;
        while (offset < data.length) {
            const tag = data[offset++];
            let length = data[offset++];
            if (length & 0x80) {
                let count = length & 0x7f;
                if (!count || count > 4) throw Error('DER');
                for (length = 0; count > 0; count--) length = length * 256 + data[offset++];
            }
            if (offset + length > data.length) throw Error('DER');
            out.push({ tag, value: data.subarray(offset, offset + length) });
            offset += length;
        }
        return out;
    }

    function base64ToBytes(text) {
        const raw = atob(text.replace(/\s/g, ''));
        return Uint8Array.from(raw, character => character.charCodeAt(0));
    }

    function bytesToBase64(data) {
        let raw = '';
        for (let i = 0; i < data.length; i += 0x8000) raw += String.fromCharCode(...data.subarray(i, i + 0x8000));
        return btoa(raw);
    }

    function toPem(data, label) {
        return '-----BEGIN ' + label + '-----\n' + bytesToBase64(data).match(/.{1,64}/g).join('\n') + '\n-----END ' + label + '-----\n';
    }

    async function cipherKey(password, salt, iterations, hash, bits, usage) {
        const material = await subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveKey']);
        return subtle.deriveKey({ name: 'PBKDF2', salt, iterations, hash }, material, { name: 'AES-CBC', length: bits }, false, [usage]);
    }

    /* The PKCS#8 private key (ArrayBuffer), encrypted with the password: an "ENCRYPTED PRIVATE KEY" PEM. */
    async function protectPrivateKey(pkcs8, password) {
        if (!password || password.length < 8) throw Error('Mật khẩu bảo vệ khóa riêng cần ít nhất 8 ký tự.');
        const salt = random(16), iv = random(16);
        const key = await cipherKey(password, salt, ITERATIONS, 'SHA-256', 256, 'encrypt');
        const encrypted = new Uint8Array(await subtle.encrypt({ name: 'AES-CBC', iv }, key, pkcs8));
        const kdf = der(0x30, der(0x06, OID.pbkdf2),
            der(0x30, der(0x04, salt), integer(ITERATIONS), der(0x30, der(0x06, OID.hmacSha256), der(0x05))));
        const scheme = der(0x30, der(0x06, OID.aes256), der(0x04, iv));
        const algorithm = der(0x30, der(0x06, OID.pbes2), der(0x30, kdf, scheme));
        return toPem(der(0x30, algorithm, der(0x04, encrypted)), 'ENCRYPTED PRIVATE KEY');
    }

    /* The PKCS#8 bytes of a key file. An encrypted file needs its password; an old unprotected file needs none. */
    async function openPrivateKey(pem, password) {
        const match = /-----BEGIN ([A-Z ]+)-----([\s\S]+?)-----END \1-----/.exec(pem || '');
        if (!match) throw Error('File không phải khóa riêng dạng PEM.');
        const data = base64ToBytes(match[2]);
        if (match[1] === 'PRIVATE KEY') return data;
        if (match[1] !== 'ENCRYPTED PRIVATE KEY') throw Error('Cần file khóa riêng PKCS#8 (PRIVATE KEY hoặc ENCRYPTED PRIVATE KEY).');
        if (!password) throw Error('Khóa riêng này được bảo vệ bằng mật khẩu. Hãy nhập mật khẩu.');
        let salt, iterations, hash, bits, iv, encrypted;
        try {
            const [algorithm, body] = elements(elements(data)[0].value);
            const [scheme, parameters] = elements(algorithm.value);
            const [kdf, cipher] = elements(parameters.value);
            const [kdfId, kdfParameters] = elements(kdf.value);
            const [cipherId, cipherIv] = elements(cipher.value);
            if (!same(scheme.value, OID.pbes2) || !same(kdfId.value, OID.pbkdf2)) throw Error('scheme');
            const fields = elements(kdfParameters.value);
            salt = fields[0].value;
            iterations = fields[1].value.reduce((total, digit) => total * 256 + digit, 0);
            const prf = fields.find(field => field.tag === 0x30);
            const prfId = prf ? elements(prf.value)[0].value : OID.hmacSha1;
            hash = same(prfId, OID.hmacSha256) ? 'SHA-256' : same(prfId, OID.hmacSha512) ? 'SHA-512' : same(prfId, OID.hmacSha1) ? 'SHA-1' : null;
            bits = same(cipherId.value, OID.aes256) ? 256 : same(cipherId.value, OID.aes128) ? 128 : 0;
            iv = cipherIv.value;
            encrypted = body.value;
            if (!hash || !bits || iv.length !== 16 || !iterations) throw Error('scheme');
        } catch (error) {
            throw Error('Kiểu mã hóa của file khóa riêng không được hỗ trợ (cần PBES2, PBKDF2 và AES-CBC).');
        }
        try {
            const key = await cipherKey(password, salt, iterations, hash, bits, 'decrypt');
            return new Uint8Array(await subtle.decrypt({ name: 'AES-CBC', iv }, key, encrypted));
        } catch (error) {
            throw Error('Sai mật khẩu khóa riêng.');
        }
    }

    const api = { protectPrivateKey, openPrivateKey };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.KeyProtection = api;
})(typeof window !== 'undefined' ? window : globalThis);
