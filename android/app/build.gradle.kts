// Build configuration (Gradle Kotlin DSL). The application itself is written in
// Java with XML layouts: there is no Kotlin or Jetpack Compose source code.
plugins {
    alias(libs.plugins.android.application)
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
        viewBinding = true
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

dependencies {
    implementation(libs.androidx.appcompat)
    implementation(libs.material)
    implementation(libs.androidx.lifecycle.viewmodel)
    implementation(libs.androidx.lifecycle.livedata)
    implementation(libs.media3.exoplayer)
    implementation(libs.media3.exoplayer.rtsp)
    implementation(libs.media3.ui)

    testImplementation(libs.junit)
    testImplementation(libs.org.json)
}
