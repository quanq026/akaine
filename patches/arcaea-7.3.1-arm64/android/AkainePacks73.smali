.class final Lorg/cocos2dx/lib/AkainePacks73;
.super Ljava/lang/Object;

.method private static native prepareNative()Z
.end method

.method static prepare()V
    .registers 1

    :try_start
    const-string v0, "akaine_packs73"
    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V
    invoke-static {}, Lorg/cocos2dx/lib/AkainePacks73;->prepareNative()Z
    :try_end
    .catch Ljava/lang/LinkageError; {:try_start .. :try_end} :failed
    return-void

    :failed
    move-exception v0
    return-void
.end method
