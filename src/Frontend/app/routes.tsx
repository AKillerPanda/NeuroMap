import { createBrowserRouter } from "react-router";
import { Home } from "./pages/Home";
import { Workspace } from "./pages/Workspace";
import { Graph } from "./pages/Graph";
import { EnhancedGraph } from "./pages/EnhancedGraph";
import { LearningPath } from "./pages/LearningPath";
import { NotFound } from "./pages/NotFound";

export const router = createBrowserRouter([
  {
    path: "/",
    children: [
      { index: true, Component: Home },
      { path: "workspace", Component: Workspace },
      { path: "graph", Component: Graph },
      { path: "graph/:skill", Component: EnhancedGraph },
      { path: "path", Component: LearningPath },
      { path: "*", Component: NotFound },
    ],
  },
]);
