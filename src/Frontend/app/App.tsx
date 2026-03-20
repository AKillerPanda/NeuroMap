import { RouterProvider } from "react-router";
import { router } from "./routes";
import { TopicsProvider } from "./context/TopicsContext";
import { Toaster } from "./components/ui/sonner";

function App() {
  return (
    <TopicsProvider>
      <RouterProvider router={router} />
      <Toaster />
    </TopicsProvider>
  );
}

export default App;