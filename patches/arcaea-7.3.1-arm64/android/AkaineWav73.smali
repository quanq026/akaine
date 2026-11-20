.class final Lorg/cocos2dx/lib/AkaineWav73;
.super Ljava/lang/Object;

.field private static loaded:Z
.field private static unavailable:Z

.method private static native nativeResume(Ljava/lang/String;)V
.end method

.method private static native nativePause()V
.end method

.method static resume()V
    .registers 2

    :try_start
    sget-boolean v0, Lorg/cocos2dx/lib/AkaineWav73;->unavailable:Z
    if-nez v0, :done
    invoke-static {}, Lorg/cocos2dx/lib/Cocos2dxHelper;->getActivity()Landroid/app/Activity;
    move-result-object v0
    if-eqz v0, :done
    invoke-virtual {v0}, Landroid/app/Activity;->getFilesDir()Ljava/io/File;
    move-result-object v0
    if-eqz v0, :done
    invoke-virtual {v0}, Ljava/io/File;->getAbsolutePath()Ljava/lang/String;
    move-result-object v0
    sget-boolean v1, Lorg/cocos2dx/lib/AkaineWav73;->loaded:Z
    if-nez v1, :activate
    const-string v1, "akaine_wav73"
    invoke-static {v1}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V
    const/4 v1, 0x1
    sput-boolean v1, Lorg/cocos2dx/lib/AkaineWav73;->loaded:Z
    :activate
    invoke-static {v0}, Lorg/cocos2dx/lib/AkaineWav73;->nativeResume(Ljava/lang/String;)V
    :try_end
    .catch Ljava/lang/LinkageError; {:try_start .. :try_end} :link_error
    .catch Ljava/lang/RuntimeException; {:try_start .. :try_end} :failed
    :done
    return-void

    :link_error
    move-exception v0
    const/4 v1, 0x1
    sput-boolean v1, Lorg/cocos2dx/lib/AkaineWav73;->unavailable:Z
    return-void

    :failed
    move-exception v0
    return-void
.end method

.method static pause()V
    .registers 1

    sget-boolean v0, Lorg/cocos2dx/lib/AkaineWav73;->loaded:Z
    if-eqz v0, :done
    :try_start
    invoke-static {}, Lorg/cocos2dx/lib/AkaineWav73;->nativePause()V
    :try_end
    .catch Ljava/lang/LinkageError; {:try_start .. :try_end} :failed
    :done
    return-void
    :failed
    move-exception v0
    return-void
.end method
