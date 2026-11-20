# Shared patch source

These reusable runtime and build inputs support the [7.3.1 port](../arcaea-7.3.1-arm64/). The port owns its version-specific addresses and Android bindings.

The AKFC loader uses prefixed static crypto. Build it with [build_boringssl_android.py](../../scripts/build_boringssl_android.py) when assembling the native loader.
