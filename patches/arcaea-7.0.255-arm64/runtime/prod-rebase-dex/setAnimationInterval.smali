.method public static setAnimationInterval(F)V
    .registers 6

    const v0, 0x4e6e6b28    # 1.0E9f

    mul-float/2addr p0, v0

    float-to-long v0, p0

    const-wide/32 v2, 0xfe502c

    cmp-long v4, v0, v2

    if-nez v4, :cond_23

    :try_start_c
    invoke-static {}, Llow/moe/AppActivity;->getDisplayRefreshRate()F

    move-result v2
    :try_end_10
    .catch Ljava/lang/Exception; {:try_start_c .. :try_end_10} :catch_22

    const v3, 0x426ff5c3    # 59.99f

    cmpl-float v4, v2, v3

    if-ltz v4, :cond_23

    const v3, 0x42700a3d    # 60.01f

    cmpg-float v4, v2, v3

    if-gtz v4, :cond_23

    const-wide/32 v0, 0xfe502a

    goto :goto_23

    :catch_22
    move-exception v2

    .line 71
    :cond_23
    :goto_23
    sput-wide v0, Lorg/cocos2dx/lib/Cocos2dxRenderer;->sAnimationInterval:J

    return-void
.end method
