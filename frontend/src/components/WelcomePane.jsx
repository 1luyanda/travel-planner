import { workspaceImages } from '../data/destinationImages'
import { starterPrompts } from '../data/starterPrompts'
import styles from '../workspace.module.css'

export default function WelcomePane({ onPrompt, composerRef }) {
  return (
    <div className={styles.welcome}>
      <img
        className={styles.welcomeMark}
        src={workspaceImages.welcomeMark.src}
        alt=""
        width="88"
        height="88"
      />
      <h1>Where to today?</h1>
      <p>
        Tell me a mood, a budget, and where you are leaving from. Results come from stored travel data
        and are ranked in the browser — not a live search or AI planner.
      </p>
      <div className={styles.starters} role="group" aria-label="Starter prompts">
        {starterPrompts.map((prompt) => (
          <button key={prompt} type="button" onClick={() => onPrompt(prompt)}>
            {prompt}
          </button>
        ))}
      </div>
      <button type="button" className={styles.textLink} onClick={() => composerRef?.current?.focus()}>
        Or type your own request
      </button>
    </div>
  )
}
