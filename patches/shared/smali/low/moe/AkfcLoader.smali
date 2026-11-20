.class public Llow/moe/AkfcLoader;
.super Ljava/lang/Object;
.source "AkfcLoader.java"

.method public constructor <init>()V
    .locals 0
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    return-void
.end method

.method public static init()V
    .locals 1
    :try_start_0
    const-string v0, "akfcloader"
    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V
    invoke-static {}, Llow/moe/AkfcLoader;->installHooks()Z
    :try_end_0
    .catch Ljava/lang/UnsatisfiedLinkError; {:try_start_0 .. :try_end_0} :catch_0
    :catch_0
    return-void
.end method

.method public static native installHooks()Z
.end method

.method public static native wipeDecrypted()V
.end method
