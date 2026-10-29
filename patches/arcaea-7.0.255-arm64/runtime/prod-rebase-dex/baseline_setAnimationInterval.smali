.method public static setAnimationInterval(F)V
    .registers 3

    const v0, 0x4e6e6b28    # 1.0E9f

    mul-float/2addr p0, v0

    float-to-long v0, p0

    .line 71
    sput-wide v0, Lorg/cocos2dx/lib/Cocos2dxRenderer;->sAnimationInterval:J

    return-void
.end method
