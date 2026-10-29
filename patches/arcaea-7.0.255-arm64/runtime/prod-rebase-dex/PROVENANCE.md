# Finite production DEX normalization

The baseline method is from authentic production V9 `classes3.dex` SHA256
`d1e5f99fe8cbad8760906437c033156f892ca4f338eb7764f70568b87c06d27a`.
The replacement is the accepted staging input method whose complete DEX SHA256
is `6372ea45d2abdf921b2cd29ba86317bd33845f057dd77c8d8660cc997350c274`.
Both were compared using the pinned RawDexTool/baksmali toolchain.

Only `Cocos2dxRenderer.setAnimationInterval(F)V` changes. The method converts
16,666,668ns to 16,666,666ns when display refresh is 59.99–60.01Hz; all other
requests and display-query exceptions retain the original interval. All 724
other classes, renderer methods and class metadata are unchanged.

The builder starts from actual production APK members, validates the exact
method preimage, assembles this source change, disassembles it again and requires
the known complete normalized DEX SHA256. No final DEX is copied as a build input.
