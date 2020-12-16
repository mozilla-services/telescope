import { html } from "../../htm_preact.mjs";

const Markdown = ({ md }) => {
  const innerHTML = {
    __html: marked(md),
  };

  return html`<div dangerouslySetInnerHTML="${innerHTML}" />`;
}

export default Markdown;
