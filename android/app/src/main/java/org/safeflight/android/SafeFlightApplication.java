package org.safeflight.android;

import android.app.Application;

/** Application class (declared in AndroidManifest.xml): creates the {@link AppContainer}. */
public final class SafeFlightApplication extends Application {
    private AppContainer container;

    @Override
    public void onCreate() {
        super.onCreate();
        container = new AppContainer(this);
    }

    public AppContainer getContainer() {
        return container;
    }
}
