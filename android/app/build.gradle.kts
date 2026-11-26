plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Numéro de compilation GitHub : chaque nouvelle APK a un numéro plus grand.
val buildNumber = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()

android {
    namespace = "com.jv.audiobox"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.jv.audiobox"
        minSdk = 26
        targetSdk = 35
        versionCode = buildNumber
        versionName = "1.0.$buildNumber"
    }

    // La clé de signature vient des secrets GitHub (le dépôt est public) :
    // ANDROID_KEYSTORE_B64 et ANDROID_KEYSTORE_PASSWORD. Ne jamais la changer,
    // sinon les mises à jour ne s'installeront plus par-dessus.
    signingConfigs {
        create("fixe") {
            storeFile = file(System.getenv("KEYSTORE_FILE") ?: "keystore/audiobox.jks")
            storeType = "jks"
            storePassword = System.getenv("KEYSTORE_PASSWORD") ?: ""
            keyAlias = "audiobox"
            keyPassword = System.getenv("KEYSTORE_PASSWORD") ?: ""
        }
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("fixe")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
    }
    lint {
        checkReleaseBuilds = false
        abortOnError = false
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
}
