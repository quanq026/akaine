// akfc_loader.cpp — Native AKFC decryption loader for Arcaea fan charts
//
// Hooks fopen() in libcocos2dcpp.so via PLT/GOT patching.
// If a .aff file with AKFC magic is opened, decrypts to temp file.
//
// Uses system arm64 libcrypto.so via dlsym (no headers needed).
// Build: aarch64-linux-android24-clang++ -shared -fPIC -o libakfcloader.so \
//        akfc_loader.cpp -llog -ldl
#include <jni.h>
#include <android/log.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <elf.h>
#include <string>
#include <vector>
#include <map>
#include <stdint.h>
#include <stdarg.h>
#include <fcntl.h>
#include <pthread.h>
#include <errno.h>
#include <sys/ptrace.h>

#define TAG "AKFCLoader"
#define LOGI(...) ((void)0)
#define LOGW(...) ((void)0)
#define LOGE(...) ((void)0)
#define LOGD(...) ((void)0)

// AKFC header: <4sBBHIQHBB32s32s> = 96 bytes
#pragma pack(push, 1)
struct AkfcHeader {
    char magic[4];
    uint8_t version;
    uint8_t flags;
    uint16_t header_size;
    uint32_t key_epoch;
    uint64_t plaintext_size;
    uint16_t wrapped_key_size;
    uint8_t nonce_size;
    uint8_t tag_size;
    uint8_t context_hash[32];
    uint8_t plaintext_sha256[32];
};
#pragma pack(pop)
static const size_t AKFC_HEADER_SIZE = sizeof(AkfcHeader);

// ===== OpenSSL types and function pointers (loaded via dlsym) =====
// Forward-declare opaque types (no headers needed)
struct evp_cipher_ctx_st;
struct evp_cipher_st;
struct evp_md_st;
struct evp_pkey_st;
struct evp_pkey_ctx_st;
struct engine_st;
struct evp_aead_st;
struct evp_aead_ctx_st;
typedef struct evp_cipher_ctx_st EVP_CIPHER_CTX;
typedef struct evp_cipher_st EVP_CIPHER;
typedef struct evp_md_st EVP_MD;
typedef struct evp_pkey_st EVP_PKEY;
typedef struct evp_pkey_ctx_st EVP_PKEY_CTX;
typedef struct engine_st ENGINE;
typedef struct evp_aead_st EVP_AEAD;
typedef struct evp_aead_ctx_st EVP_AEAD_CTX;

static const EVP_MD* (*p_EVP_sha256)(void) = nullptr;
static const EVP_MD* (*p_EVP_sha1)(void) = nullptr;
static const EVP_CIPHER* (*p_EVP_aes_256_gcm)(void) = nullptr;
static EVP_CIPHER_CTX* (*p_EVP_CIPHER_CTX_new)(void) = nullptr;
static void (*p_EVP_CIPHER_CTX_free)(EVP_CIPHER_CTX*) = nullptr;
static int (*p_EVP_DecryptInit_ex)(EVP_CIPHER_CTX*, const EVP_CIPHER*, ENGINE*, const unsigned char*, const unsigned char*) = nullptr;
static int (*p_EVP_DecryptUpdate)(EVP_CIPHER_CTX*, unsigned char*, int*, const unsigned char*, int) = nullptr;
static int (*p_EVP_DecryptFinal_ex)(EVP_CIPHER_CTX*, unsigned char*, int*) = nullptr;
static int (*p_EVP_CIPHER_CTX_ctrl)(EVP_CIPHER_CTX*, int, int, void*) = nullptr;
static EVP_PKEY* (*p_d2i_AutoPrivateKey)(EVP_PKEY*, const unsigned char**, long) = nullptr;
static void (*p_EVP_PKEY_free)(EVP_PKEY*) = nullptr;
static EVP_PKEY_CTX* (*p_EVP_PKEY_CTX_new)(EVP_PKEY*, ENGINE*) = nullptr;
static void (*p_EVP_PKEY_CTX_free)(EVP_PKEY_CTX*) = nullptr;
static int (*p_EVP_PKEY_decrypt_init)(EVP_PKEY_CTX*) = nullptr;
static int (*p_EVP_PKEY_decrypt)(EVP_PKEY_CTX*, unsigned char*, size_t*, const unsigned char*, size_t) = nullptr;
// RSA padding controls
static int (*p_EVP_PKEY_CTX_set_rsa_padding)(EVP_PKEY_CTX*, int) = nullptr;
static int (*p_EVP_PKEY_CTX_set_rsa_oaep_md)(EVP_PKEY_CTX*, const EVP_MD*) = nullptr;
static int (*p_EVP_PKEY_CTX_set_rsa_mgf1_md)(EVP_PKEY_CTX*, const EVP_MD*) = nullptr;

// Constants (from OpenSSL headers)
#define RSA_PKCS1_OAEP_PADDING 4
#define EVP_CTRL_GCM_SET_TAG 0x15

// EVP_AEAD function pointers (BoringSSL native API)
static const EVP_AEAD* (*p_EVP_aead_aes_256_gcm)(void) = nullptr;
static EVP_AEAD_CTX* (*p_EVP_AEAD_CTX_new)(const EVP_AEAD*, const uint8_t*, size_t, size_t) = nullptr;
static void (*p_EVP_AEAD_CTX_free)(EVP_AEAD_CTX*) = nullptr;
static int (*p_EVP_AEAD_CTX_open)(EVP_AEAD_CTX*, uint8_t*, size_t*, size_t, const uint8_t*, size_t, const uint8_t*, size_t, const uint8_t*, size_t) = nullptr;

static void* g_libcrypto = nullptr;

static bool load_crypto() {
    if (g_libcrypto) return true;

    g_libcrypto = dlopen("libcrypto.so", RTLD_NOW);
    if (!g_libcrypto) {
        // Try arm64 path for ndk_translation
        g_libcrypto = dlopen("/system/lib64/arm64/libcrypto.so", RTLD_NOW);
    }
    if (!g_libcrypto) {
        LOGE("Cannot load libcrypto.so: %s", dlerror());
        return false;
    }

    #define LOAD_SYM(name) p_##name = (decltype(p_##name))dlsym(g_libcrypto, #name); \
        if (!p_##name) { LOGE("Cannot find %s: %s", #name, dlerror()); return false; }

    LOAD_SYM(EVP_sha256);
    LOAD_SYM(EVP_sha1);
    LOAD_SYM(EVP_aes_256_gcm);
    LOAD_SYM(EVP_CIPHER_CTX_new);
    LOAD_SYM(EVP_CIPHER_CTX_free);
    LOAD_SYM(EVP_DecryptInit_ex);
    LOAD_SYM(EVP_DecryptUpdate);
    LOAD_SYM(EVP_DecryptFinal_ex);
    LOAD_SYM(EVP_CIPHER_CTX_ctrl);
    LOAD_SYM(d2i_AutoPrivateKey);
    LOAD_SYM(EVP_PKEY_free);
    LOAD_SYM(EVP_PKEY_CTX_new);
    LOAD_SYM(EVP_PKEY_CTX_free);
    LOAD_SYM(EVP_PKEY_decrypt_init);
    LOAD_SYM(EVP_PKEY_decrypt);

    // These may be macros or inline in some BoringSSL versions
    // Try to load them; if they fail, we'll use alternative approach
    p_EVP_PKEY_CTX_set_rsa_padding = (decltype(p_EVP_PKEY_CTX_set_rsa_padding))dlsym(g_libcrypto, "EVP_PKEY_CTX_set_rsa_padding");
    p_EVP_PKEY_CTX_set_rsa_oaep_md = (decltype(p_EVP_PKEY_CTX_set_rsa_oaep_md))dlsym(g_libcrypto, "EVP_PKEY_CTX_set_rsa_oaep_md");
    p_EVP_PKEY_CTX_set_rsa_mgf1_md = (decltype(p_EVP_PKEY_CTX_set_rsa_mgf1_md))dlsym(g_libcrypto, "EVP_PKEY_CTX_set_rsa_mgf1_md");

    if (!p_EVP_PKEY_CTX_set_rsa_padding) {
        // BoringSSL uses EVP_PKEY_CTX_ctrl for RSA padding
        LOGW("EVP_PKEY_CTX_set_rsa_padding not found, will use ctrl");
    }

    // Load EVP_AEAD functions (BoringSSL native API)
    p_EVP_aead_aes_256_gcm = (decltype(p_EVP_aead_aes_256_gcm))dlsym(g_libcrypto, "EVP_aead_aes_256_gcm");
    p_EVP_AEAD_CTX_new = (decltype(p_EVP_AEAD_CTX_new))dlsym(g_libcrypto, "EVP_AEAD_CTX_new");
    p_EVP_AEAD_CTX_free = (decltype(p_EVP_AEAD_CTX_free))dlsym(g_libcrypto, "EVP_AEAD_CTX_free");
    p_EVP_AEAD_CTX_open = (decltype(p_EVP_AEAD_CTX_open))dlsym(g_libcrypto, "EVP_AEAD_CTX_open");

    if (p_EVP_aead_aes_256_gcm && p_EVP_AEAD_CTX_new && p_EVP_AEAD_CTX_open) {
        LOGI("EVP_AEAD API available (BoringSSL native)");
    } else {
        LOGW("EVP_AEAD API not available, will use EVP_CIPHER API");
    }

    LOGI("libcrypto.so loaded successfully");
    return true;
}

// Helper: set RSA OAEP padding via ctrl if direct functions unavailable
static int set_oaep_padding(EVP_PKEY_CTX* ctx) {
    if (p_EVP_PKEY_CTX_set_rsa_padding) {
        return p_EVP_PKEY_CTX_set_rsa_padding(ctx, RSA_PKCS1_OAEP_PADDING);
    }
    // Fallback: use EVP_PKEY_CTX_ctrl
    // EVP_PKEY_CTRL_RSA_PADDING = 0x100 + 2 = 0x102
    // This is a fallback and may not work on all versions
    typedef int (*ctrl_fn)(EVP_PKEY_CTX*, int, int, void*);
    static ctrl_fn p_ctrl = (ctrl_fn)dlsym(g_libcrypto, "EVP_PKEY_CTX_ctrl");
    if (p_ctrl) {
        return p_ctrl(ctx, 0x102, RSA_PKCS1_OAEP_PADDING, nullptr);
    }
    return -1;
}

static int set_oaep_md(EVP_PKEY_CTX* ctx, const EVP_MD* md) {
    if (p_EVP_PKEY_CTX_set_rsa_oaep_md) {
        return p_EVP_PKEY_CTX_set_rsa_oaep_md(ctx, md);
    }
    typedef int (*ctrl_fn)(EVP_PKEY_CTX*, int, int, void*);
    static ctrl_fn p_ctrl = (ctrl_fn)dlsym(g_libcrypto, "EVP_PKEY_CTX_ctrl");
    if (p_ctrl) {
        // EVP_PKEY_CTRL_RSA_OAEP_MD = 0x100 + 6 = 0x106
        return p_ctrl(ctx, 0x106, 0, (void*)md);
    }
    return -1;
}

static int set_mgf1_md(EVP_PKEY_CTX* ctx, const EVP_MD* md) {
    if (p_EVP_PKEY_CTX_set_rsa_mgf1_md) {
        return p_EVP_PKEY_CTX_set_rsa_mgf1_md(ctx, md);
    }
    typedef int (*ctrl_fn)(EVP_PKEY_CTX*, int, int, void*);
    static ctrl_fn p_ctrl = (ctrl_fn)dlsym(g_libcrypto, "EVP_PKEY_CTX_ctrl");
    if (p_ctrl) {
        // EVP_PKEY_CTRL_RSA_MGF1_MD = 0x100 + 7 = 0x107
        return p_ctrl(ctx, 0x107, 0, (void*)md);
    }
    return -1;
}

// ===== File operations =====
static FILE* (*real_fopen)(const char* path, const char* mode) = nullptr;
static std::vector<std::string> g_tempFiles;

static void* find_real_fopen() {
    void* ptr = dlsym(RTLD_DEFAULT, "fopen");
    if (!ptr) {
        void* libc = dlopen("libc.so", RTLD_NOW);
        if (libc) {
            ptr = dlsym(libc, "fopen");
            dlclose(libc);
        }
    }
    return ptr;
}

// Decrypt AKFC container
static std::vector<uint8_t> decrypt_akfc(const uint8_t* data, size_t data_len, const char* file_path) {
    if (data_len < AKFC_HEADER_SIZE) {
        LOGE("Data too small: %zu", data_len);
        return {};
    }

    AkfcHeader header;
    memcpy(&header, data, AKFC_HEADER_SIZE);

    if (memcmp(header.magic, "AKFC", 4) != 0) {
        LOGE("Bad magic: %c%c%c%c", header.magic[0], header.magic[1], header.magic[2], header.magic[3]);
        return {};
    }

    LOGI("AKFC: version=%d epoch=%u pt_size=%llu wrapped=%u nonce=%d tag=%d",
         header.version, header.key_epoch,
         (unsigned long long)header.plaintext_size,
         header.wrapped_key_size, header.nonce_size, header.tag_size);

    size_t offset = AKFC_HEADER_SIZE;
    const uint8_t* wrapped_key = data + offset;
    offset += header.wrapped_key_size;
    const uint8_t* nonce = data + offset;
    offset += header.nonce_size;
    const uint8_t* ciphertext = data + offset;
    const uint8_t* tag = data + offset + header.plaintext_size;

    // Validate total size — file must be complete before decrypting
    size_t expected_size = offset + header.plaintext_size + header.tag_size;
    if (data_len < expected_size) {
        LOGE("File incomplete: have %zu, need %zu (pt=%llu)", data_len, expected_size,
             (unsigned long long)header.plaintext_size);
        return {};
    }

    // Load RSA private key from embedded obfuscated data (XOR + double XOR)
    #include "embedded_key.h"
    std::vector<uint8_t> key_data(EMBEDDED_KEY_SIZE);
    // Layer 1: XOR with key
    for (int i = 0; i < EMBEDDED_KEY_SIZE; i++) {
        key_data[i] = EMBEDDED_KEY_DATA[i] ^ EMBEDDED_KEY_XOR[i % 32];
    }
    // Layer 2: XOR with offset pattern (harder to extract via simple XOR analysis)
    for (int i = 0; i < EMBEDDED_KEY_SIZE; i++) {
        key_data[i] ^= (uint8_t)((i * 0x37 + 0x5A) & 0xFF);
    }
    long key_len = EMBEDDED_KEY_SIZE;
    LOGI("RSA key (embedded): %ld bytes", key_len);

    // Parse DER private key
    const unsigned char* key_ptr = key_data.data();
    EVP_PKEY* pkey = p_d2i_AutoPrivateKey(nullptr, &key_ptr, key_len);
    if (!pkey) {
        LOGE("Failed to parse RSA key");
        return {};
    }

    // RSA unwrap DEK
    EVP_PKEY_CTX* ctx = p_EVP_PKEY_CTX_new(pkey, nullptr);
    if (!ctx) {
        LOGE("Failed to create PKEY ctx");
        p_EVP_PKEY_free(pkey);
        return {};
    }

    if (p_EVP_PKEY_decrypt_init(ctx) <= 0) {
        LOGE("Failed to init RSA decrypt");
        p_EVP_PKEY_CTX_free(ctx);
        p_EVP_PKEY_free(pkey);
        return {};
    }

    if (set_oaep_padding(ctx) <= 0) {
        LOGE("Failed to set OAEP padding");
        p_EVP_PKEY_CTX_free(ctx);
        p_EVP_PKEY_free(pkey);
        return {};
    }
    set_oaep_md(ctx, p_EVP_sha256());
    set_mgf1_md(ctx, p_EVP_sha1());

    size_t dek_len = 0;
    if (p_EVP_PKEY_decrypt(ctx, nullptr, &dek_len, wrapped_key, header.wrapped_key_size) <= 0) {
        LOGE("Failed to get DEK size");
        p_EVP_PKEY_CTX_free(ctx);
        p_EVP_PKEY_free(pkey);
        return {};
    }

    std::vector<uint8_t> dek(dek_len);
    if (p_EVP_PKEY_decrypt(ctx, dek.data(), &dek_len, wrapped_key, header.wrapped_key_size) <= 0) {
        LOGE("Failed to unwrap DEK");
        p_EVP_PKEY_CTX_free(ctx);
        p_EVP_PKEY_free(pkey);
        return {};
    }

    LOGI("DEK unwrapped: %zu bytes", dek_len);
    p_EVP_PKEY_CTX_free(ctx);
    p_EVP_PKEY_free(pkey);

    // Build AAD
    char sha256_hex[65];
    for (int i = 0; i < 32; i++) {
        sprintf(sha256_hex + i * 2, "%02x", header.plaintext_sha256[i]);
    }
    sha256_hex[64] = '\0';

    // Parse song_id and file_name from file_path
    // Path format: .../songs/{song_id}/{file_name} or .../dl_{song_id}/{file_name}
    std::string path(file_path ? file_path : "");
    std::string song_id = "unknown";
    std::string file_name = "unknown.aff";

    // Path formats:
    //   /data/.../files/dl/{song_id}_{difficulty}       (e.g. seishunno_hacking_0)
    //   /data/.../files/dl/{song_id}_{difficulty}.tmp   (e.g. seishunno_hacking_1.tmp)
    //   /data/.../songs/{song_id}/{file_name}           (e.g. songs/seishunno_hacking/0.aff)
    size_t last_slash = path.rfind('/');
    if (last_slash != std::string::npos) {
        std::string basename = path.substr(last_slash + 1);
        // Strip .tmp extension if present
        std::string base_no_tmp = basename;
        if (base_no_tmp.size() > 4 && base_no_tmp.substr(base_no_tmp.size() - 4) == ".tmp") {
            base_no_tmp = base_no_tmp.substr(0, base_no_tmp.size() - 4);
        }

        // Check if path contains /dl/ — format: {song_id}_{difficulty}
        if (path.find("/dl/") != std::string::npos) {
            // Find last underscore followed by a single digit
            size_t us_pos = base_no_tmp.rfind('_');
            if (us_pos != std::string::npos && us_pos + 1 < base_no_tmp.size()) {
                std::string diff_str = base_no_tmp.substr(us_pos + 1);
                // Validate it's a single digit (0,1,2,4)
                if (diff_str.size() == 1 && (diff_str[0] == '0' || diff_str[0] == '1' ||
                    diff_str[0] == '2' || diff_str[0] == '3' || diff_str[0] == '4')) {
                    song_id = base_no_tmp.substr(0, us_pos);
                    file_name = diff_str + ".aff";
                }
            }
        }
        // Check if path contains /songs/ — format: {song_id}/{file_name}
        else if (path.find("/songs/") != std::string::npos) {
            size_t prev_slash = path.rfind('/', last_slash - 1);
            if (prev_slash != std::string::npos) {
                song_id = path.substr(prev_slash + 1, last_slash - prev_slash - 1);
                file_name = basename;
            }
        }
    }
    LOGI("AAD: release=fan-sec-v1 song=%s file=%s (path=%s)", song_id.c_str(), file_name.c_str(), path.c_str());

    std::string aad = std::string("AKFC1\n") +
                      "fan-sec-v1\n" +
                      song_id + "\n" +
                      file_name + "\n" +
                      std::to_string(header.key_epoch) + "\n" +
                      std::to_string(header.plaintext_size) + "\n" +
                      sha256_hex;

    // Try EVP_AEAD API first (BoringSSL native)
    if (p_EVP_aead_aes_256_gcm && p_EVP_AEAD_CTX_new && p_EVP_AEAD_CTX_open) {
        LOGI("Using EVP_AEAD API for AES-256-GCM");

        const EVP_AEAD* aead = p_EVP_aead_aes_256_gcm();
        EVP_AEAD_CTX* aead_ctx = p_EVP_AEAD_CTX_new(aead, dek.data(), dek_len, header.tag_size);
        if (!aead_ctx) {
            LOGE("Failed to create EVP_AEAD_CTX");
            return {};
        }

        // EVP_AEAD_CTX_open expects ciphertext + tag concatenated
        std::vector<uint8_t> ct_and_tag(header.plaintext_size + header.tag_size);
        memcpy(ct_and_tag.data(), ciphertext, header.plaintext_size);
        memcpy(ct_and_tag.data() + header.plaintext_size, tag, header.tag_size);

        std::vector<uint8_t> plaintext(header.plaintext_size);
        size_t out_len = 0;
        int rc = p_EVP_AEAD_CTX_open(aead_ctx,
            plaintext.data(), &out_len, plaintext.size(),
            nonce, header.nonce_size,
            ct_and_tag.data(), ct_and_tag.size(),
            (const uint8_t*)aad.data(), aad.size());

        p_EVP_AEAD_CTX_free(aead_ctx);

        if (rc != 1) {
            LOGE("EVP_AEAD_CTX_open failed (rc=%d)", rc);
            return {};
        }

        LOGI("Decrypted via EVP_AEAD: %zu bytes", out_len);
        plaintext.resize(out_len);
        return plaintext;
    }

    // Fallback: EVP_CIPHER API (OpenSSL-style)
    LOGI("Using EVP_CIPHER API for AES-256-GCM");
    EVP_CIPHER_CTX* cctx = p_EVP_CIPHER_CTX_new();
    if (!cctx) {
        LOGE("Failed to create cipher ctx");
        return {};
    }

    if (p_EVP_DecryptInit_ex(cctx, p_EVP_aes_256_gcm(), nullptr, nullptr, nullptr) != 1) {
        LOGE("Failed to init AES-GCM");
        p_EVP_CIPHER_CTX_free(cctx);
        return {};
    }

    if (p_EVP_DecryptInit_ex(cctx, nullptr, nullptr, dek.data(), nonce) != 1) {
        LOGE("Failed to set key/IV");
        p_EVP_CIPHER_CTX_free(cctx);
        return {};
    }

    // AAD already built above
    int out_len;
    if (p_EVP_DecryptUpdate(cctx, nullptr, &out_len,
                            (const unsigned char*)aad.data(), (int)aad.size()) != 1) {
        LOGE("Failed to set AAD");
        p_EVP_CIPHER_CTX_free(cctx);
        return {};
    }

    std::vector<uint8_t> plaintext(header.plaintext_size);
    if (p_EVP_DecryptUpdate(cctx, plaintext.data(), &out_len,
                            ciphertext, (int)header.plaintext_size) != 1) {
        LOGE("Failed to decrypt");
        p_EVP_CIPHER_CTX_free(cctx);
        return {};
    }
    int total_len = out_len;

    // Set tag — BoringSSL may return 0 or 1 for success
    LOGI("Setting GCM tag: %d bytes", header.tag_size);
    std::vector<uint8_t> tag_copy(tag, tag + header.tag_size);
    int ctrl_ret = p_EVP_CIPHER_CTX_ctrl(cctx, EVP_CTRL_GCM_SET_TAG, header.tag_size, tag_copy.data());
    LOGI("ctrl returned: %d", ctrl_ret);
    if (ctrl_ret < 0) {
        // Try with the tag pointer directly
        ctrl_ret = p_EVP_CIPHER_CTX_ctrl(cctx, EVP_CTRL_GCM_SET_TAG, header.tag_size, (void*)tag);
        LOGI("ctrl (direct ptr) returned: %d", ctrl_ret);
        if (ctrl_ret < 0) {
            LOGE("Failed to set GCM tag (ret=%d)", ctrl_ret);
            p_EVP_CIPHER_CTX_free(cctx);
            return {};
        }
    }

    if (p_EVP_DecryptFinal_ex(cctx, plaintext.data() + total_len, &out_len) != 1) {
        LOGE("GCM auth failed!");
        p_EVP_CIPHER_CTX_free(cctx);
        return {};
    }
    total_len += out_len;

    LOGI("Decrypted: %d bytes", total_len);
    p_EVP_CIPHER_CTX_free(cctx);

    plaintext.resize(total_len);
    return plaintext;
}

// memfd_create — create anonymous file in RAM (no disk writes)
#include <sys/syscall.h>
#include <unistd.h>

#ifndef __NR_memfd_create
#define __NR_memfd_create 279  // arm64
#endif

#ifndef MFD_CLOEXEC
#define MFD_CLOEXEC 0x0001
#endif

#ifndef MFD_ALLOW_SEALING
#define MFD_ALLOW_SEALING 0x0002
#endif

static int memfd_create_wrapper(const char* name, unsigned int flags) {
    return syscall(__NR_memfd_create, name, flags);
}

// Cache: map original path -> {memfd_path, plaintext_size}
struct MemfdEntry {
    std::string memfd_path;  // /proc/self/fd/N
    size_t plaintext_size;
};
static std::map<std::string, MemfdEntry> g_memfdCache;
static pthread_mutex_t g_memfdMutex = PTHREAD_MUTEX_INITIALIZER;

// Lookup plaintext size for a path (for stat hooks)
static size_t get_cached_plaintext_size(const char* path) {
    pthread_mutex_lock(&g_memfdMutex);
    auto it = g_memfdCache.find(path);
    if (it != g_memfdCache.end()) {
        size_t sz = it->second.plaintext_size;
        pthread_mutex_unlock(&g_memfdMutex);
        return sz;
    }
    pthread_mutex_unlock(&g_memfdMutex);
    return 0;
}

static std::string write_temp_file(const std::vector<uint8_t>& data, const char* original_path) {
    // Strategy: Overwrite original file with plaintext.
    // This is the only approach that works with game's download flow:
    // - Game downloads .tmp files in parallel
    // - When first file completes, game opens ALL files
    // - Files still downloading (.tmp) are skipped (incomplete)
    // - Game retries later — by then, completed files are already plaintext
    // - stat() returns correct plaintext size (no hook needed)
    //
    // Security: file is in app private dir (root only), anti-debug blocks
    // Frida/debugger, key is double-XOR obfuscated, symbols stripped.
    std::string path(original_path);

    // Check cache — already decrypted?
    pthread_mutex_lock(&g_memfdMutex);
    auto it = g_memfdCache.find(path);
    if (it != g_memfdCache.end()) {
        pthread_mutex_unlock(&g_memfdMutex);
        LOGI("Already decrypted: %s", path.c_str());
        return path;
    }
    pthread_mutex_unlock(&g_memfdMutex);

    FILE* f = real_fopen ? real_fopen(path.c_str(), "wb") : fopen(path.c_str(), "wb");
    if (!f) {
        LOGE("Failed to overwrite: %s", path.c_str());
        return "";
    }
    fwrite(data.data(), 1, data.size(), f);
    fclose(f);
    chmod(path.c_str(), 0666);

    // Track for wipe on exit
    pthread_mutex_lock(&g_memfdMutex);
    g_memfdCache[path] = {path, data.size()};
    pthread_mutex_unlock(&g_memfdMutex);

    LOGI("Decrypted to disk: %s (%zu bytes)", path.c_str(), data.size());
    return path;
}

// Wipe — overwrite with zeros + delete all decrypted files
static void wipe_decrypted_files() {
    pthread_mutex_lock(&g_memfdMutex);
    for (auto& kv : g_memfdCache) {
        const std::string& path = kv.first;
        // Overwrite with zeros to prevent file recovery
        FILE* f = fopen(path.c_str(), "wb");
        if (f) {
            std::vector<uint8_t> zeros(kv.second.plaintext_size, 0);
            fwrite(zeros.data(), 1, zeros.size(), f);
            fclose(f);
            remove(path.c_str());
            LOGI("Wiped: %s", path.c_str());
        }
    }
    g_memfdCache.clear();
    pthread_mutex_unlock(&g_memfdMutex);
    LOGI("All decrypted files wiped");
}

// Check if file is complete (download finished). Non-blocking.
static bool is_file_complete(const char* path) {
    FILE* f = real_fopen ? real_fopen(path, "rb") : fopen(path, "rb");
    if (!f) return false;
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (size < AKFC_HEADER_SIZE) {
        fclose(f);
        return false;
    }
    AkfcHeader header;
    size_t n = fread(&header, 1, AKFC_HEADER_SIZE, f);
    fclose(f);
    if (n != AKFC_HEADER_SIZE || memcmp(header.magic, "AKFC", 4) != 0) {
        return false;
    }
    size_t expected = AKFC_HEADER_SIZE + header.wrapped_key_size + header.nonce_size
                     + header.plaintext_size + header.tag_size;
    return (size_t)size >= expected;
}

// Downloader may open a .tmp immediately after one parallel request finishes
// while another request is still flushing the same song's files. If we return
// the encrypted .tmp in that window, the game hashes AKFC bytes and marks the
// download as failed. Wait briefly for the completed container size instead.
static bool wait_for_file_complete(const char* path, int timeout_ms) {
    if (is_file_complete(path)) return true;
    const int step_ms = 25;
    int waited = 0;
    while (waited < timeout_ms) {
        usleep(step_ms * 1000);
        waited += step_ms;
        if (is_file_complete(path)) {
            LOGI("File completed after wait: %s (%d ms)", path, waited);
            return true;
        }
    }
    return false;
}

static bool is_akfc_file(const char* path) {
    if (!path) return false;
    // Check extension: .aff, .tmp, or files in songs/dl paths
    const char* ext = strrchr(path, '.');
    bool ext_ok = (ext && (strcmp(ext, ".aff") == 0 || strcmp(ext, ".tmp") == 0));
    bool path_ok = (strstr(path, "/songs/") || strstr(path, "/dl/") || strstr(path, "/dl_"));
    if (!ext_ok && !path_ok) return false;

    FILE* f = real_fopen ? real_fopen(path, "rb") : fopen(path, "rb");
    if (!f) return false;
    char magic[4];
    size_t n = fread(magic, 1, 4, f);
    fclose(f);
    return (n == 4 && memcmp(magic, "AKFC", 4) == 0);
}

static std::vector<uint8_t> read_file(const char* path) {
    FILE* f = real_fopen ? real_fopen(path, "rb") : fopen(path, "rb");
    if (!f) return {};
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    std::vector<uint8_t> data(size);
    size_t n = fread(data.data(), 1, size, f);
    fclose(f);
    if ((long)n != size) return {};
    return data;
}

// Our fopen hook
static FILE* hooked_fopen(const char* path, const char* mode) {
    if (!path || !mode) return real_fopen(path, mode);

    // Only intercept read modes
    if (strcmp(mode, "rb") != 0 && strcmp(mode, "r") != 0 && strcmp(mode, "rb+") != 0) {
        return real_fopen(path, mode);
    }

    if (!is_akfc_file(path)) {
        return real_fopen(path, mode);
    }

    LOGI("AKFC fopen detected: %s", path);

    // Wait for download to complete (file may still be downloading as .tmp)
    if (!wait_for_file_complete(path, 2000)) {
        LOGI("File incomplete (still downloading), skipping: %s", path);
        return real_fopen(path, mode);
    }

    auto container = read_file(path);
    if (container.empty()) {
        LOGE("Failed to read: %s", path);
        return nullptr;
    }

    auto plaintext = decrypt_akfc(container.data(), container.size(), path);
    if (plaintext.empty()) {
        LOGE("Failed to decrypt: %s", path);
        return real_fopen(path, mode);
    }

    std::string tmp_path = write_temp_file(plaintext, path);
    if (tmp_path.empty()) return real_fopen(path, mode);

    return real_fopen(tmp_path.c_str(), mode);
}

// Real open function pointer
static int (*real_open)(const char*, int, ...) = nullptr;
static int (*real_open_2)(const char*, int) = nullptr;

// __open_2 declaration (fortified variant)
extern "C" int __open_2(const char* path, int flags);

// Our open hook — intercepts open() for .aff files
static int hooked_open(const char* path, int flags, ...) {
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = va_arg(args, int);
        va_end(args);
    }

    if (!path || (flags & (O_WRONLY | O_RDWR | O_CREAT | O_TRUNC | O_APPEND))) {
        // Not a simple read-only open
        return real_open ? real_open(path, flags, mode) : open(path, flags, mode);
    }

    if (!is_akfc_file(path)) {
        return real_open ? real_open(path, flags, mode) : open(path, flags, mode);
    }

    LOGI("AKFC open detected: %s", path);

    if (!wait_for_file_complete(path, 2000)) {
        LOGI("File incomplete (still downloading), skipping: %s", path);
        return real_open ? real_open(path, flags, mode) : open(path, flags, mode);
    }

    auto container = read_file(path);
    if (container.empty()) {
        LOGE("Failed to read: %s", path);
        return -1;
    }

    auto plaintext = decrypt_akfc(container.data(), container.size(), path);
    if (plaintext.empty()) {
        LOGE("Failed to decrypt: %s", path);
        return real_open ? real_open(path, flags, mode) : open(path, flags, mode);
    }

    std::string tmp_path = write_temp_file(plaintext, path);
    if (tmp_path.empty()) return real_open ? real_open(path, flags, mode) : open(path, flags, mode);

    return real_open ? real_open(tmp_path.c_str(), flags, mode) : open(tmp_path.c_str(), flags, mode);
}

// __open_2 hook (fortified variant — no mode arg)
static int hooked_open_2(const char* path, int flags) {
    if (!path || (flags & (O_WRONLY | O_RDWR | O_CREAT | O_TRUNC | O_APPEND))) {
        return real_open_2 ? real_open_2(path, flags) : __open_2(path, flags);
    }

    if (!is_akfc_file(path)) {
        return real_open_2 ? real_open_2(path, flags) : __open_2(path, flags);
    }

    LOGI("AKFC __open_2 detected: %s", path);

    if (!wait_for_file_complete(path, 2000)) {
        LOGI("File incomplete (still downloading), skipping: %s", path);
        return real_open_2 ? real_open_2(path, flags) : __open_2(path, flags);
    }

    auto container = read_file(path);
    if (container.empty()) {
        LOGE("Failed to read: %s", path);
        return -1;
    }

    auto plaintext = decrypt_akfc(container.data(), container.size(), path);
    if (plaintext.empty()) {
        LOGE("Failed to decrypt: %s", path);
        return real_open_2 ? real_open_2(path, flags) : __open_2(path, flags);
    }

    std::string tmp_path = write_temp_file(plaintext, path);
    if (tmp_path.empty()) return real_open_2 ? real_open_2(path, flags) : __open_2(path, flags);

    return real_open_2 ? real_open_2(tmp_path.c_str(), flags) : __open_2(tmp_path.c_str(), flags);
}

// ===== stat/lstat hooks =====
// Game checks file size via stat() before/after opening.
// We return plaintext size for AKFC files so validation passes.
static int (*real_stat)(const char*, struct stat*) = nullptr;
static int (*real_lstat)(const char*, struct stat*) = nullptr;
static int (*real_fstatat)(int, const char*, struct stat*, int) = nullptr;

// Get plaintext size from AKFC header (without full decrypt)
// Only for completed files (not .tmp — those are still downloading)
static size_t get_akfc_plaintext_size(const char* path) {
    // Skip .tmp files — they're still downloading, don't patch their size
    const char* ext = strrchr(path, '.');
    if (ext && strcmp(ext, ".tmp") == 0) return 0;

    // Check cache first
    size_t cached = get_cached_plaintext_size(path);
    if (cached > 0) return cached;

    // Only check files in /dl/ directory (AKFC files)
    if (!strstr(path, "/dl/")) return 0;

    // Read header from file
    FILE* f = real_fopen ? real_fopen(path, "rb") : fopen(path, "rb");
    if (!f) return 0;
    AkfcHeader header;
    size_t n = fread(&header, 1, AKFC_HEADER_SIZE, f);
    fclose(f);
    if (n != AKFC_HEADER_SIZE || memcmp(header.magic, "AKFC", 4) != 0) return 0;
    return header.plaintext_size;
}

static int hooked_stat(const char* path, struct stat* st) {
    int rc = real_stat ? real_stat(path, st) : stat(path, st);
    if (rc == 0 && st) {
        size_t pt_size = get_akfc_plaintext_size(path);
        if (pt_size > 0) {
            st->st_size = pt_size;
            LOGI("stat patched: %s size=%zu", path, pt_size);
        }
    }
    return rc;
}

static int hooked_lstat(const char* path, struct stat* st) {
    int rc = real_lstat ? real_lstat(path, st) : lstat(path, st);
    if (rc == 0 && st) {
        size_t pt_size = get_akfc_plaintext_size(path);
        if (pt_size > 0) {
            st->st_size = pt_size;
            LOGI("lstat patched: %s size=%zu", path, pt_size);
        }
    }
    return rc;
}

static int hooked_fstatat(int dirfd, const char* path, struct stat* st, int flags) {
    int rc = real_fstatat ? real_fstatat(dirfd, path, st, flags) : fstatat(dirfd, path, st, flags);
    if (rc == 0 && st) {
        size_t pt_size = get_akfc_plaintext_size(path);
        if (pt_size > 0) {
            st->st_size = pt_size;
            LOGI("fstatat patched: %s size=%zu", path, pt_size);
        }
    }
    return rc;
}

// ===== PLT Hooking =====
struct ElfInfo {
    uintptr_t base;
    Elf64_Ehdr* ehdr;
    Elf64_Phdr* phdr;
    Elf64_Dyn* dynamic;
    Elf64_Sym* symtab;
    const char* strtab;
    Elf64_Rela* rela_plt;
    size_t rela_plt_count;
};

static bool find_module(const char* name, uintptr_t* base, size_t* size) {
    FILE* f = fopen("/proc/self/maps", "r");
    if (!f) return false;
    char line[512];
    bool found = false;
    uintptr_t mod_base = 0, mod_end = 0;
    while (fgets(line, sizeof(line), f)) {
        if (strstr(line, name)) {
            uintptr_t start, end;
            sscanf(line, "%lx-%lx", &start, &end);
            if (!found) { mod_base = start; found = true; }
            if (end > mod_end) mod_end = end;
        }
    }
    fclose(f);
    if (found) { *base = mod_base; *size = mod_end - mod_base; }
    return found;
}

static bool parse_elf(ElfInfo* info, uintptr_t base) {
    info->base = base;
    info->ehdr = (Elf64_Ehdr*)base;
    if (memcmp(info->ehdr->e_ident, ELFMAG, SELFMAG) != 0) return false;

    info->phdr = (Elf64_Phdr*)(base + info->ehdr->e_phoff);
    info->dynamic = nullptr;
    for (int i = 0; i < info->ehdr->e_phnum; i++) {
        if (info->phdr[i].p_type == PT_DYNAMIC) {
            info->dynamic = (Elf64_Dyn*)(base + info->phdr[i].p_vaddr);
            break;
        }
    }
    if (!info->dynamic) return false;

    void* symtab_ptr = nullptr;
    void* strtab_ptr = nullptr;
    void* jmprel = nullptr;
    size_t pltrelsz = 0;

    for (Elf64_Dyn* d = info->dynamic; d->d_tag != DT_NULL; d++) {
        switch (d->d_tag) {
            case DT_SYMTAB: symtab_ptr = (void*)(uintptr_t)(base + d->d_un.d_ptr); break;
            case DT_STRTAB: strtab_ptr = (void*)(uintptr_t)(base + d->d_un.d_ptr); break;
            case DT_JMPREL: jmprel = (void*)(uintptr_t)(base + d->d_un.d_ptr); break;
            case DT_PLTRELSZ: pltrelsz = d->d_un.d_val; break;
        }
    }
    if (!symtab_ptr || !strtab_ptr || !jmprel || !pltrelsz) {
        LOGE("Missing dynamic entries: sym=%p str=%p jmp=%p sz=%zu",
             symtab_ptr, strtab_ptr, jmprel, pltrelsz);
        return false;
    }

    // Validate addresses are within reasonable range
    if ((uintptr_t)symtab_ptr < base || (uintptr_t)strtab_ptr < base) {
        LOGE("DT addresses seem invalid (below base)");
        return false;
    }

    info->symtab = (Elf64_Sym*)symtab_ptr;
    info->strtab = (const char*)strtab_ptr;
    info->rela_plt = (Elf64_Rela*)jmprel;
    info->rela_plt_count = pltrelsz / sizeof(Elf64_Rela);
    return true;
}

static void** find_got_entry(ElfInfo* info, const char* func_name) {
    for (size_t i = 0; i < info->rela_plt_count; i++) {
        Elf64_Rela* rela = &info->rela_plt[i];
        uint32_t sym_idx = ELF64_R_SYM(rela->r_info);

        // Safety: check sym_idx is reasonable
        if (sym_idx > 100000) continue;

        Elf64_Sym* sym = &info->symtab[sym_idx];
        const char* name = info->strtab + sym->st_name;

        // Safety: check name pointer
        if ((uintptr_t)name < info->base) continue;

        if (strcmp(name, func_name) == 0) {
            void** got = (void**)(info->base + rela->r_offset);
            LOGI("Found %s GOT at %p (val=%p)", func_name, got, *got);
            return got;
        }
    }
    return nullptr;
}

static bool hook_fopen_in_module(const char* module_name) {
    uintptr_t base, size;
    if (!find_module(module_name, &base, &size)) {
        LOGE("Module not found: %s", module_name);
        return false;
    }
    LOGI("Module %s: base=0x%lx size=%lu", module_name, base, size);

    ElfInfo info;
    if (!parse_elf(&info, base)) {
        LOGE("ELF parse failed");
        return false;
    }
    LOGI("ELF: %zu PLT relocs", info.rela_plt_count);

    bool any_hooked = false;

    // Hook fopen
    void** got = (void**)find_got_entry(&info, "fopen");
    if (!got) got = (void**)find_got_entry(&info, "fopen64");
    if (got) {
        real_fopen = (FILE* (*)(const char*, const char*))*got;
        uintptr_t page = (uintptr_t)got & ~0xFFFL;
        if (mprotect((void*)page, 4096 * 2, PROT_READ | PROT_WRITE) == 0) {
            *got = (void*)hooked_fopen;
            mprotect((void*)page, 4096 * 2, PROT_READ);
            LOGI("fopen hooked! real=%p hook=%p", real_fopen, hooked_fopen);
            any_hooked = true;
        } else {
            LOGE("mprotect failed for fopen");
        }
    } else {
        LOGW("fopen not in PLT");
    }

    // Hook open
    void** got_open = (void**)find_got_entry(&info, "open");
    if (got_open) {
        real_open = (int (*)(const char*, int, ...))*got_open;
        uintptr_t page = (uintptr_t)got_open & ~0xFFFL;
        if (mprotect((void*)page, 4096 * 2, PROT_READ | PROT_WRITE) == 0) {
            *got_open = (void*)hooked_open;
            mprotect((void*)page, 4096 * 2, PROT_READ);
            LOGI("open hooked! real=%p hook=%p", real_open, hooked_open);
            any_hooked = true;
        } else {
            LOGE("mprotect failed for open");
        }
    } else {
        LOGW("open not in PLT");
    }

    // Hook __open_2
    void** got_open2 = (void**)find_got_entry(&info, "__open_2");
    if (got_open2) {
        real_open_2 = (int (*)(const char*, int))*got_open2;
        uintptr_t page = (uintptr_t)got_open2 & ~0xFFFL;
        if (mprotect((void*)page, 4096 * 2, PROT_READ | PROT_WRITE) == 0) {
            *got_open2 = (void*)hooked_open_2;
            mprotect((void*)page, 4096 * 2, PROT_READ);
            LOGI("__open_2 hooked! real=%p hook=%p", real_open_2, hooked_open_2);
            any_hooked = true;
        } else {
            LOGE("mprotect failed for __open_2");
        }
    } else {
        LOGW("__open_2 not in PLT");
    }

    // Hook stat
    void** got_stat = (void**)find_got_entry(&info, "stat");
    if (got_stat) {
        real_stat = (int (*)(const char*, struct stat*))*got_stat;
        uintptr_t page = (uintptr_t)got_stat & ~0xFFFL;
        if (mprotect((void*)page, 4096 * 2, PROT_READ | PROT_WRITE) == 0) {
            *got_stat = (void*)hooked_stat;
            mprotect((void*)page, 4096 * 2, PROT_READ);
            LOGI("stat hooked! real=%p", real_stat);
            any_hooked = true;
        }
    } else {
        LOGW("stat not in PLT");
    }

    // Hook lstat
    void** got_lstat = (void**)find_got_entry(&info, "lstat");
    if (got_lstat) {
        real_lstat = (int (*)(const char*, struct stat*))*got_lstat;
        uintptr_t page = (uintptr_t)got_lstat & ~0xFFFL;
        if (mprotect((void*)page, 4096 * 2, PROT_READ | PROT_WRITE) == 0) {
            *got_lstat = (void*)hooked_lstat;
            mprotect((void*)page, 4096 * 2, PROT_READ);
            LOGI("lstat hooked! real=%p", real_lstat);
            any_hooked = true;
        }
    } else {
        LOGW("lstat not in PLT");
    }

    // Hook fstatat
    void** got_fstatat = (void**)find_got_entry(&info, "fstatat");
    if (got_fstatat) {
        real_fstatat = (int (*)(int, const char*, struct stat*, int))*got_fstatat;
        uintptr_t page = (uintptr_t)got_fstatat & ~0xFFFL;
        if (mprotect((void*)page, 4096 * 2, PROT_READ | PROT_WRITE) == 0) {
            *got_fstatat = (void*)hooked_fstatat;
            mprotect((void*)page, 4096 * 2, PROT_READ);
            LOGI("fstatat hooked! real=%p", real_fstatat);
            any_hooked = true;
        }
    } else {
        LOGW("fstatat not in PLT");
    }

    return any_hooked;
}

// ===== Anti-debug =====
static bool is_debugged() {
    // Check /proc/self/status for TracerPid
    FILE* f = fopen("/proc/self/status", "r");
    if (!f) return false;
    char line[256];
    bool traced = false;
    while (fgets(line, sizeof(line), f)) {
        if (strncmp(line, "TracerPid:", 10) == 0) {
            int pid = atoi(line + 10);
            if (pid > 0) {
                traced = true;
            }
            break;
        }
    }
    fclose(f);
    return traced;
}

// Check if frida-server or common debug tools are running
static bool is_frida_present() {
    FILE* f = fopen("/proc/self/maps", "r");
    if (!f) return false;
    char line[512];
    bool found = false;
    while (fgets(line, sizeof(line), f)) {
        if (strstr(line, "frida") || strstr(line, "gum-js") || strstr(line, "gadget")) {
            found = true;
            break;
        }
    }
    fclose(f);
    return found;
}

static bool security_check() {
    if (is_debugged()) {
        LOGE("Debugger detected — refusing to install hooks");
        return false;
    }
    if (is_frida_present()) {
        LOGE("Frida detected — refusing to install hooks");
        return false;
    }
    return true;
}

// ===== JNI =====
extern "C" JNIEXPORT jboolean JNICALL
Java_low_moe_AkfcLoader_installHooks(JNIEnv*, jclass) {
    LOGI("Installing AKFC hooks...");

    // Anti-debug check
    if (!security_check()) {
        return JNI_FALSE;
    }

    if (!load_crypto()) return JNI_FALSE;
    if (!real_fopen) {
        real_fopen = (FILE* (*)(const char*, const char*))find_real_fopen();
        if (!real_fopen) { LOGE("No real fopen"); return JNI_FALSE; }
    }
    if (!hook_fopen_in_module("libcocos2dcpp.so")) {
        LOGW("libcocos2dcpp.so hook failed, trying alternatives...");
        if (!hook_fopen_in_module("cocos2dcpp.so")) return JNI_FALSE;
    }
    LOGI("AKFC hooks installed");
    return JNI_TRUE;
}

extern "C" JNIEXPORT void JNICALL
Java_low_moe_AkfcLoader_wipeDecrypted(JNIEnv*, jclass) {
    LOGI("Wiping all decrypted files...");
    wipe_decrypted_files();
}

__attribute__((constructor))
static void on_load() {
    LOGI("=== AKFC Loader loaded ===");
    load_crypto();
    real_fopen = (FILE* (*)(const char*, const char*))find_real_fopen();
    if (real_fopen) {
        LOGI("real_fopen=%p", real_fopen);
        // Don't auto-hook here — wait for JNI installHooks call
        // (libcocos2dcpp.so may not be fully initialized yet)
    } else {
        LOGE("Cannot find fopen!");
    }
}

