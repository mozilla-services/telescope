import { html } from "../../htm_preact.min.mjs";

const Markdown = ({ md }) => {
  const innerHTML = {
    __html: marked.parse(md),
  };

  return html`<div dangerouslySetInnerHTML="${innerHTML}" />`;
};

export default Markdown;
