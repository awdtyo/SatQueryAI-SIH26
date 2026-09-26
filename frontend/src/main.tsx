import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import BootGate from "./components/boot/BootGate";
import { MissionStatusProvider } from "./hooks/useMissionStatus";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MissionStatusProvider>
      <BootGate>
        <App />
      </BootGate>
    </MissionStatusProvider>
  </React.StrictMode>,
);
