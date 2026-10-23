plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

// Release signing comes only from the environment (CI secrets or a local
// shell). No keystore, password or alias is ever stored in this repository.
// Without all four variables the release build is produced unsigned.
val releaseKeystore = providers.environmentVariable("ENGINEVERSE_KEYSTORE_FILE").orNull
val releaseStorePassword = providers.environmentVariable("ENGINEVERSE_KEYSTORE_PASSWORD").orNull
val releaseKeyAlias = providers.environmentVariable("ENGINEVERSE_KEY_ALIAS").orNull
val releaseKeyPassword = providers.environmentVariable("ENGINEVERSE_KEY_PASSWORD").orNull
val canSignRelease = listOf(releaseKeystore, releaseStorePassword, releaseKeyAlias, releaseKeyPassword)
    .all { !it.isNullOrBlank() } && file(releaseKeystore!!).isFile

android {
    namespace = "io.github.sauravprivatelimited369byte.engineverse"
    compileSdk = 36

    defaultConfig {
        applicationId = "io.github.sauravprivatelimited369byte.engineverse"
        minSdk = 24
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"
        // The public website this app opens for full notes and the playground.
        buildConfigField("String", "SITE_URL", "\"https://sauravprivatelimited369-byte.github.io/Engine_Verse/\"")
        buildConfigField("String", "REPO_URL", "\"https://github.com/sauravprivatelimited369-byte/Engine_Verse\"")
    }

    signingConfigs {
        if (canSignRelease) {
            create("release") {
                storeFile = file(releaseKeystore!!)
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (canSignRelease) signingConfig = signingConfigs.getByName("release")
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

    lint {
        abortOnError = true
        warningsAsErrors = false
        checkReleaseBuilds = true
    }

    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.core.splashscreen)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    debugImplementation(libs.androidx.compose.ui.tooling)

    testImplementation(libs.junit)
}
