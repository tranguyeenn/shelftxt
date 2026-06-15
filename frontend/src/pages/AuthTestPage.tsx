import { useEffect } from "react";

import { supabase } from "@/lib/supabase";

export function AuthTestPage() {
  useEffect(() => {
    async function test() {
      const {
        data: { session },
      } = await supabase.auth.getSession();

      console.log("session:", session);
    }

    test();
  }, []);

  return <div>Auth Test</div>;
}