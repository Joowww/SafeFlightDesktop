# Release builds are not minified yet (isMinifyEnabled = false).
# kotlinx.serialization keeps generated serializers when minification is enabled.
-keepclassmembers class org.safeflight.android.** {
    *** Companion;
    kotlinx.serialization.KSerializer serializer(...);
}
