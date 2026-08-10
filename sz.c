#include <wolfssl/options.h>
#include <wolfssl/wolfcrypt/random.h>
#include <wolfssl/wolfcrypt/aes.h>
#include <stdio.h>
int main(void) {
    printf("sizeof(WC_RNG)=%zu\n", sizeof(WC_RNG));
    printf("sizeof(Aes)=%zu\n", sizeof(Aes));
    return 0;
}