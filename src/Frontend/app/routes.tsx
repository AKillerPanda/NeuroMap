import { createBrowserRouter } from "react-router";
import { Home } from "./pages/Home";
import { Workspace } from "./pages/Workspace";
import { Graph } from "./pages/Graph";
import { LearningPath } from "./pages/LearningPath";
import { NotFound } from "./pages/NotFound";

export const router = createBrowserRouter([
  {
    path: "/",
    children: [
      { index: true, Component: Home },
      { path: "workspace", Component: Workspace },
      { path: "graph", Component: Graph },
      { path: "path", Component: LearningPath },
      { path: "*", Component: NotFound },
    ],
  },
]);
