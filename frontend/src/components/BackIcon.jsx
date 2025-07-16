import { ArrowLeft } from "lucide-react";          // npm i lucide-react
import { useNavigate } from "react-router-dom";

export default function BackIcon() {
  const nav = useNavigate();
  return (
    <button className="p-2" onClick={() => nav(-1)}>
      <ArrowLeft className="w-6 h-6 text-black" />
    </button>
  );
}
