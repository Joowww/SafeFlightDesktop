package org.safeflight.android.control;

import org.junit.Test;
import org.safeflight.android.mavlink.MavlinkIds;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

/**
 * Structural safety checks on the application source (src/main): the app is
 * Java only, and it has no way to send a vehicle command.
 */
public class SafetyStructureTest {
    // Unit tests run with the module directory (android/app) as working directory.
    private static final File MAIN = new File("src/main");

    private static List<File> files(File dir, String suffix) {
        List<File> out = new ArrayList<>();
        File[] children = dir.listFiles();
        if (children == null) {
            return out;
        }
        for (File f : children) {
            if (f.isDirectory()) {
                out.addAll(files(f, suffix));
            } else if (f.getName().endsWith(suffix)) {
                out.add(f);
            }
        }
        return out;
    }

    private static String read(File f) throws IOException {
        return new String(Files.readAllBytes(f.toPath()), StandardCharsets.UTF_8);
    }

    @Test
    public void applicationSourcesAreJavaOnly() {
        assertTrue("source folder not found: " + MAIN.getAbsolutePath(), MAIN.isDirectory());
        assertEquals("Kotlin files in src/main", 0, files(MAIN, ".kt").size());
        assertTrue(files(MAIN, ".java").size() > 30);
    }

    @Test
    public void onlyTheGcsHeartbeatIsEverSent() throws IOException {
        List<String> senders = new ArrayList<>();
        for (File f : files(MAIN, ".java")) {
            if (read(f).contains(".send(")) {
                senders.add(f.getName());
            }
        }
        // MavlinkClient sends exactly the frames produced by GcsHeartbeatEncoder.
        assertEquals(List.of("MavlinkClient.java"), senders);
        String client = read(new File(MAIN, "java/org/safeflight/android/mavlink/MavlinkClient.java"));
        assertTrue(client.contains("byte[] frame = encoder.encode();"));
    }

    @Test
    public void noCommandMessageIsDeclared() {
        // COMMAND_LONG, COMMAND_INT, SET_MODE, MISSION_COUNT, MISSION_ITEM_INT,
        // SET_POSITION_TARGET_LOCAL_NED, RC_CHANNELS_OVERRIDE, PARAM_SET.
        for (int id : new int[] {76, 75, 11, 44, 73, 84, 70, 23}) {
            assertNull("message id " + id + " must not be supported", MavlinkIds.crcExtra(id));
        }
    }
}
