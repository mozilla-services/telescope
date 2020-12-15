import { Component, html } from "../../htm_preact.mjs";

export default class TimeAgo extends Component {
  constructor() {
    super();
    this.refresh = this.refresh.bind(this);
    this.state = {
      timeago: "some time ago",
      timeoutId: null,
    }
  }

  componentDidMount() {
    this.refresh();
  }

  componentDidUpdate(prevProps, prevState) {
    const { date } = this.props;
    const { timeoutId } = this.state;
    if (prevState.timeoutId && timeoutId !== prevState.timeoutId) {
      clearTimeout(prevState.timeoutId);
    }

    const isDateNewlySet = date && !prevProps.date;
    const isDateChanged = date &&  prevProps.date && date.getTime() !== prevProps.date.getTime();
    if (isDateNewlySet || isDateChanged) {
      clearTimeout(timeoutId);
      this.refresh();
    }
  }

  componentWillUnmount() {
    const { timeoutId } = this.state;
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
  }

  refresh() {
    const { date } = this.props;

    if (date) {
      // Determine how often to refresh the timeago value
      const now = new Date();
      const timedelta = Math.abs(now.getTime() - date.getTime());
      let timeoutDuration;
      if (timedelta < 60 * 1000) {
        timeoutDuration = 1000;
      } else if (timedelta < 60 * 60 * 1000) {
        timeoutDuration = 60 * 1000;
      } else if (timedelta < 24 * 60 * 60 * 1000) {
        timeoutDuration = 10 * 60 * 1000;
      } else {
        timeoutDuration = 60 * 60 * 1000;
      }

      const timeoutId = setTimeout(this.refresh, timeoutDuration);

      this.setState({
        timeago: timeago().format(date),
        timeoutId,
      });
    }
  }

  render({ date }) {
    const isoDate = date ? date.toISOString() : '';
    const title = date ? date.toString() : '';
    return html`
      <time datetime="${isoDate}" title="${title}">
        ${this.state.timeago}
      </time>
    `;
  }
}
