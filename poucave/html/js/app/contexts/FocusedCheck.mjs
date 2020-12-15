import { createContext } from "../../htm_preact.mjs";

const FocusedCheck = createContext({
  project: null,
  name: null,
  setValue: () => {},
});

export default FocusedCheck;
