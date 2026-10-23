import { z } from "zod";

// Zod probes `new Function` to compile faster parsers. The Content-Security-Policy
// forbids eval, so every page load reported the blocked probe in the console;
// jitless skips the probe and parses the same way, just without compiling.
z.config({ jitless: true });
