#pragma once
#include <jni.h>

// Only the existing GL-thread JNI callback supplies this environment. No attach,
// new thread, global reference, Java write or per-frame field read is introduced.
namespace menu_geometry_jni {
inline JNIEnv* environment = nullptr;
inline menu_geometry::Interval read() noexcept {
    menu_geometry::Interval result;
    JNIEnv* env = environment;
    if (!env) return result;
    // Never consume an exception owned by the application.
    if (env->ExceptionCheck()) { result.error = 2; return result; }
    jclass type = env->FindClass("org/cocos2dx/lib/Cocos2dxRenderer");
    if (env->ExceptionCheck()) {
        env->ExceptionClear(); if (type) env->DeleteLocalRef(type);
        result.error = 3; return result;
    }
    if (!type) { result.error = 3; return result; }
    jfieldID field = env->GetStaticFieldID(type, "sAnimationInterval", "J");
    if (env->ExceptionCheck()) {
        env->ExceptionClear(); env->DeleteLocalRef(type); result.error = 4; return result;
    }
    if (!field) { env->DeleteLocalRef(type); result.error = 4; return result; }
    const jlong value = env->GetStaticLongField(type, field);
    if (env->ExceptionCheck()) {
        env->ExceptionClear(); env->DeleteLocalRef(type); result.error = 5; return result;
    }
    env->DeleteLocalRef(type);
    result.value = static_cast<long long>(value); result.error = 0;
    return result;
}
inline void capture(JNIEnv* env) noexcept {
    if (!menu_geometry::owner_ready()) return;
    environment = env;
    menu_geometry::interval_reader = &read;
}
} // namespace menu_geometry_jni
