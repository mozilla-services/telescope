import { createContext } from "../../htm_preact.mjs";

const SelectedTags = createContext({
  tags: [],
  add: () => {},
  remove: () => {},
});

export default SelectedTags;
