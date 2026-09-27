import { TripPlanner } from "@/components/TripPlanner";

export default function Home() {
  return (
    <main>
      <nav className="research-entry" aria-label="Research">
        <a href="/research">Explore live destination research →</a>
        {" · "}
        <a href="/demo">Offline mock demo</a>
      </nav>
      <TripPlanner live />
    </main>
  );
}
