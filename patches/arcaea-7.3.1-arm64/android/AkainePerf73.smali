.class public final Lorg/cocos2dx/lib/AkainePerf73;
.super Ljava/lang/Object;

.field private static loaded:Z
.field private static lastRate:F

.method public static prepare()V
    .registers 2

    :try_start_0
    const/4 v0, 0x0

    sput v0, Lorg/cocos2dx/lib/AkainePerf73;->lastRate:F

    sget-boolean v0, Lorg/cocos2dx/lib/AkainePerf73;->loaded:Z

    if-nez v0, :cond_e

    const-string v0, "akaine_perf73"

    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V

    const/4 v0, 0x1

    sput-boolean v0, Lorg/cocos2dx/lib/AkainePerf73;->loaded:Z

    :cond_e
    invoke-static {}, Lorg/cocos2dx/lib/AkainePerf73;->prepareNative()Z
    :try_end_11
    .catch Ljava/lang/LinkageError; {:try_start_0 .. :try_end_11} :catch_12
    .catch Ljava/lang/RuntimeException; {:try_start_0 .. :try_end_11} :catch_12

    return-void

    :catch_12
    move-exception v0

    return-void
.end method

.method public static applyFrameRate(J)V
    .registers 6

    :try_start_0
    sget v0, Landroid/os/Build$VERSION;->SDK_INT:I

    const/16 v1, 0x1e

    if-lt v0, v1, :cond_31

    const-wide/32 v0, 0xfe502c

    cmp-long v2, p0, v0

    if-nez v2, :cond_10

    const/high16 p0, 0x42700000    # 60.0f

    goto :goto_12

    :cond_10
    const/high16 p0, 0x42f00000    # 120.0f

    :goto_12
    sget p1, Lorg/cocos2dx/lib/AkainePerf73;->lastRate:F

    cmpl-float p1, p1, p0

    if-eqz p1, :cond_31

    invoke-static {}, Lorg/cocos2dx/lib/Cocos2dxGLSurfaceView;->getInstance()Lorg/cocos2dx/lib/Cocos2dxGLSurfaceView;

    move-result-object p1

    if-eqz p1, :cond_31

    invoke-virtual {p1}, Landroid/view/SurfaceView;->getHolder()Landroid/view/SurfaceHolder;

    move-result-object p1

    if-eqz p1, :cond_31

    invoke-interface {p1}, Landroid/view/SurfaceHolder;->getSurface()Landroid/view/Surface;

    move-result-object p1

    if-eqz p1, :cond_31

    const/4 v0, 0x1

    invoke-virtual {p1, p0, v0}, Landroid/view/Surface;->setFrameRate(FI)V

    sput p0, Lorg/cocos2dx/lib/AkainePerf73;->lastRate:F
    :try_end_31
    .catchall {:try_start_0 .. :try_end_31} :catch_31

    :catch_31
    :cond_31
    return-void
.end method

.method private static native prepareNative()Z
.end method

.method public static native paceCap60(J)J
.end method
