plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// Single version source shared with SafeFlight Desktop (../VERSION).
val safeflightVersion: String = rootProject.file("../VERSION").readText().trim()
val versionParts = safeflightVersion.split(".").map { it.toIntOrNull() ?: 0 } + listOf(0, 0, 0)
val computedVersionCode = versionParts[0] * 10000 + versionParts[1] * 100 + versionParts[2]

android {
    namespace = "org.safeflight.android"
    compileSdk = 36

    defaultConfig {
        applicationId = "org.safeflight.android"
        // SIYI MK32 runs Android 9 (API 28); API 26 leaves margin for other handsets.
        minSdk = 26
        targetSdk = 35
        versionCode = computedVersionCode
        versionName = safeflightVersion
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            // Release signing is intentionally not configured in the repository.
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    sourceSets {
        // Shared contracts (MAVLink vectors, profile examples) used by unit tests.
        getByName("test").resources.srcDir(rootProject.file("../shared"))
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }

    lint {
        abortOnError = true
        warningsAsErrors = false
        checkReleaseBuilds = false
        disable += setOf("GradleDependency", "NewerVersionAvailable", "AndroidGradlePluginVersion", "OldTargetApi")
    }
}

kotlin {
    // Bytecode target 17; any installed JDK >= 17 can compile it.
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.media3.exoplayer)
    implementation(libs.media3.exoplayer.rtsp)
    implementation(libs.media3.ui)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    debugImplementation(libs.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
}
