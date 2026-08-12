import Image from "next/image";

const scenarios = [
  {
    number: "01",
    era: "The early republic · 1803",
    title: "The Marshall Gambit",
    prompt: "When principle and power diverge, what should the Court protect?",
    image: "/scenes/courtroom-1803.png",
    position: "center 42%",
  },
  {
    number: "02",
    era: "Interest groups · 2009–2010",
    title: "Shaping the ACA: A Lobbyist's Gambit",
    prompt: "Can a coalition hold when every ally wants something different?",
    image: "/scenes/healthcare-coalition.png",
    position: "center 38%",
  },
  {
    number: "03",
    era: "Executive power · Present day",
    title: "The Quiet Transfer",
    prompt: "What do you preserve when the institution itself is under strain?",
    image: "/scenes/oval-office-night.png",
    position: "center 45%",
  },
];

const qualitySteps = [
  {
    number: "01",
    title: "Every route, played",
    body: "A computer traces every choice and combination—243 routes when that’s what the story demands.",
    stat: "All paths",
  },
  {
    number: "02",
    title: "Continuity, verified",
    body: "An independent editor reads each route five times. We trust patterns, not one-off noise.",
    stat: "5× review",
  },
  {
    number: "03",
    title: "Repairs, re-tested",
    body: "Every revision starts the inspection again. Regressions are discarded; the best version always survives.",
    stat: "Zero shortcuts",
  },
];

export default function HomePage() {
  return (
    <main>
      <section className="hero" id="top">
        <nav className="nav shell" aria-label="Primary navigation">
          <a className="brand" href="#top" aria-label="Branching Scenarios home">
            <span className="brand-mark" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            <span>Branching<br />Scenarios</span>
          </a>
          <div className="nav-links">
            <a href="#scenarios">Explore</a>
            <a href="#quality">How we verify</a>
            <a className="nav-cta" href="/join">Enter a class <span aria-hidden="true">↗</span></a>
          </div>
        </nav>

        <div className="hero-grid shell">
          <div className="hero-copy">
            <p className="eyebrow"><span /> History is not a straight line</p>
            <h1>What will<br />you <em>choose?</em></h1>
            <p className="hero-intro">
              Step inside the decisions that shaped our world. Every choice changes the story. Every ending is earned.
            </p>
            <div className="hero-actions">
              <a className="button button-primary" href="#scenarios">Explore scenarios <span aria-hidden="true">→</span></a>
              <a className="text-link" href="#quality"><span className="play-dot" aria-hidden="true">▶</span> See how stories are verified</a>
            </div>
          </div>

          <div className="hero-art" aria-label="Three illustrated civic decision scenarios">
            <div className="branch-map" aria-hidden="true">
              <span className="trunk" />
              <span className="branch branch-a" />
              <span className="branch branch-b" />
              <span className="branch branch-c" />
              <i className="node node-a" />
              <i className="node node-b" />
              <i className="node node-c" />
            </div>
            <div className="hero-frame frame-back">
              <Image src="/scenes/healthcare-coalition.png" alt="Healthcare professionals at a coalition press conference" fill priority sizes="(max-width: 900px) 70vw, 35vw" />
            </div>
            <div className="hero-frame frame-middle">
              <Image src="/scenes/oval-office-night.png" alt="A tense late-night meeting in the Oval Office" fill priority sizes="(max-width: 900px) 70vw, 35vw" />
            </div>
            <div className="hero-frame frame-front">
              <Image src="/scenes/courtroom-1803.png" alt="An 1803 court reading a consequential decision" fill priority sizes="(max-width: 900px) 70vw, 35vw" />
              <div className="frame-caption"><span>Now playing</span><strong>The Marshall Gambit</strong></div>
            </div>
            <div className="choice-chip chip-a">A <span>Hold the line</span></div>
            <div className="choice-chip chip-b">B <span>Build consensus</span></div>
          </div>
        </div>

        <div className="hero-footer shell">
          <span>Built for curious minds · Grades 6–12</span>
          <a href="#scenarios">Scroll to explore <i aria-hidden="true">↓</i></a>
          <span className="trust-note"><i aria-hidden="true">✓</i> Every route quality checked</span>
        </div>
      </section>

      <section className="scenario-section" id="scenarios">
        <div className="section-heading shell">
          <div>
            <p className="eyebrow eyebrow-dark"><span /> Choose a turning point</p>
            <h2>Three rooms.<br /><em>Countless outcomes.</em></h2>
          </div>
          <p>Enter a dilemma with no easy answer. The story remembers what you decide—and changes around you.</p>
        </div>

        <div className="scenario-list shell">
          {scenarios.map((scenario, index) => (
            <article className="scenario-card" key={scenario.title}>
              <div className={`scenario-image drift-${index + 1}`}>
                <Image
                  src={scenario.image}
                  alt=""
                  fill
                  sizes="(max-width: 800px) 100vw, 42vw"
                  style={{ objectPosition: scenario.position }}
                />
                <span className="card-number">{scenario.number}</span>
              </div>
              <div className="scenario-content">
                <p className="scenario-era">{scenario.era}</p>
                <h3>{scenario.title}</h3>
                <p className="scenario-prompt">“{scenario.prompt}”</p>
                <a href="#quality" aria-label={`Learn about the quality process behind ${scenario.title}`}>
                  Follow this branch <span aria-hidden="true">↗</span>
                </a>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="promise-section" id="quality">
        <div className="promise-intro shell">
          <p className="eyebrow"><span /> The promise behind every story</p>
          <h2>Your choices matter.<br />The story <em>keeps its word.</em></h2>
          <p>
            Before a scenario reaches a student—or a single final illustration is commissioned—we prove that its branches are real, its endings are reachable, and its story never contradicts the journey.
          </p>
        </div>

        <div className="quality-rail shell">
          <div className="rail-line" aria-hidden="true"><i /><i /><i /></div>
          {qualitySteps.map((step) => (
            <article className="quality-step" key={step.number}>
              <div className="quality-top"><span>{step.number}</span><strong>{step.stat}</strong></div>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </article>
          ))}
        </div>

        <div className="proof shell">
          <div className="proof-art" aria-hidden="true">
            <div className="proof-orbit orbit-one" />
            <div className="proof-orbit orbit-two" />
            <div className="proof-core">✓</div>
            <span className="proof-node n1" />
            <span className="proof-node n2" />
            <span className="proof-node n3" />
            <span className="proof-node n4" />
          </div>
          <div className="proof-copy">
            <p className="eyebrow"><span /> Tested against the hardest cases</p>
            <h2>Broken branches,<br /><em>rebuilt.</em></h2>
            <p>The weakest scenario in the library went from no meaningful choices and one reachable ending to four consequential choices, four distinct endings, and zero consistent continuity complaints—without commissioning a single new image.</p>
            <div className="metrics">
              <div><strong>4</strong><span>distinct endings</span></div>
              <div><strong>0</strong><span>continuity defects</span></div>
              <div><strong>0</strong><span>new images needed</span></div>
            </div>
          </div>
        </div>
      </section>

      <section className="closing">
        <div className="closing-image" aria-hidden="true">
          <Image src="/scenes/healthcare-coalition.png" alt="" fill sizes="100vw" />
        </div>
        <div className="closing-overlay" />
        <div className="closing-content shell">
          <p className="eyebrow"><span /> The next chapter is yours</p>
          <h2>There is more than<br />one way through history.</h2>
          <a className="button button-light" href="#scenarios">Choose your scenario <span aria-hidden="true">→</span></a>
        </div>
      </section>

      <footer className="footer shell">
        <a className="brand brand-dark" href="#top"><span className="brand-mark" aria-hidden="true"><i /><i /><i /></span><span>Branching<br />Scenarios</span></a>
        <p>Decision-making, made visible.</p>
        <div><a href="/teacher/login">Teacher sign in</a><a href="/join">Join a class</a></div>
      </footer>
    </main>
  );
}
