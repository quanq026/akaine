.method public onDrawFrame(Ljavax/microedition/khronos/opengles/GL10;)V
    .registers 6

    .line 123
    sget-wide v0, Lorg/cocos2dx/lib/Cocos2dxRenderer;->sAnimationInterval:J

    long-to-double v0, v0

    const-wide v2, 0x416fca0555555555L    # 1.6666666666666666E7

    cmpg-double p1, v0, v2

    if-gtz p1, :cond_19

    .line 124
    invoke-static {}, Lorg/cocos2dx/lib/Cocos2dxRenderer;->nativeRender()V

    invoke-static {}, Llow/moe/AnomalyMonitor;->frame()V

    .line 125
    iget p1, p0, Lorg/cocos2dx/lib/Cocos2dxRenderer;->videoFrameCount:I

    add-int/lit8 p1, p1, 0x1

    iput p1, p0, Lorg/cocos2dx/lib/Cocos2dxRenderer;->videoFrameCount:I

    goto :goto_3a

    .line 127
    :cond_19
    invoke-static {}, Ljava/lang/System;->nanoTime()J

    move-result-wide v0

    .line 128
    iget-wide v2, p0, Lorg/cocos2dx/lib/Cocos2dxRenderer;->mLastTickInNanoSeconds:J

    sub-long/2addr v0, v2

    .line 130
    sget-wide v2, Lorg/cocos2dx/lib/Cocos2dxRenderer;->sAnimationInterval:J

    cmp-long p1, v0, v2

    if-gez p1, :cond_2e

    sub-long/2addr v2, v0

    const-wide/32 v0, 0xf4240

    .line 132
    :try_start_2a
    div-long/2addr v2, v0

    invoke-static {v2, v3}, Ljava/lang/Thread;->sleep(J)V
    :try_end_2e
    .catch Ljava/lang/Exception; {:try_start_2a .. :try_end_2e} :catch_2e

    .line 139
    :catch_2e
    :cond_2e
    invoke-static {}, Ljava/lang/System;->nanoTime()J

    move-result-wide v0

    iput-wide v0, p0, Lorg/cocos2dx/lib/Cocos2dxRenderer;->mLastTickInNanoSeconds:J

    .line 140
    invoke-static {}, Lorg/cocos2dx/lib/Cocos2dxRenderer;->nativeRender()V

    invoke-static {}, Llow/moe/AnomalyMonitor;->frame()V

    .line 143
    :goto_3a
    iget-boolean p1, p0, Lorg/cocos2dx/lib/Cocos2dxRenderer;->videoSurfaceHasUpdate:Z

    if-eqz p1, :cond_46

    const/4 p1, 0x0

    .line 144
    iput-boolean p1, p0, Lorg/cocos2dx/lib/Cocos2dxRenderer;->videoSurfaceHasUpdate:Z

    .line 145
    iget-object p1, p0, Lorg/cocos2dx/lib/Cocos2dxRenderer;->videoSurfaceTexture:Landroid/graphics/SurfaceTexture;

    invoke-virtual {p1}, Landroid/graphics/SurfaceTexture;->updateTexImage()V

    :cond_46
    return-void
.end method
