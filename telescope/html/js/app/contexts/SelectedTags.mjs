import { createContext } from "../../htm_preact.min.mjs";

const SelectedTags = createContext({
  tags: [],
  add: () => {},
  remove: () => {},
});

export default SelectedTags;
