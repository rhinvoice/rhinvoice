/** Whether the page runs in the program window of the installation without Docker. */
export function inProgramWindow(target: object): boolean {
  // pywebview adds its bridge to every page its windows show.
  return "pywebview" in target;
}
