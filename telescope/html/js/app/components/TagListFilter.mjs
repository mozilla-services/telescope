import { Component, html } from "../../htm_preact.mjs";
import SelectedTags from "../contexts/SelectedTags.mjs";

export default class TagListFilter extends Component {
  render({ checks }) {
    const allTags = Array.from(
      new Set(Object.values(checks).flatMap((c) => c.tags))
    );

    return html`
      <div class="mt-4 mb-5 tags-list">
        <i class="fa fa-filter" />${" "}
        <${SelectedTags.Consumer}>
          ${(selectedTagsContext) => html`
            ${this.renderTagsList(allTags, selectedTagsContext)}
          `}
        </${SelectedTags.Consumer}>
      </div>
    `;
  }

  renderTagsList(tags, selectedTagsContext) {
    if (tags.length == 0) {
      return "";
    }
    return tags.map((tag) => {
      const active = selectedTagsContext.tags.includes(tag);
      return html`
        <a
          class="badge ${active ? "" : "active"}"
          href="#"
          onClick=${(e) => {
            e.preventDefault();
            if (active) {
              selectedTagsContext.remove(tag);
            } else {
              selectedTagsContext.add(tag);
            }
          }}
        >
          ${tag} </a
        >${" "}
      `;
    });
  }
}
