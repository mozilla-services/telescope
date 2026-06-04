import { createContext } from "../../htm_preact.min.mjs";

const FocusedCheck = createContext({
  project: null,
  name: null,
  setValue: () => {},
});

export default FocusedCheck;
