import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { JSX } from "react";

/**
 * The Loctapus brand lockup: the octopus logo beside the wordmark. The logo
 * is decorative (empty alt), so an enclosing link's accessible name comes
 * from the wordmark text alone. The root is inline-level so a centered parent
 * (the auth frame's home link) still centers the lockup as text-align does
 * not reach block-level flex children.
 */
export default function BrandMark({ size = 28 }: { size?: number }): JSX.Element {
  return (
    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 1 }}>
      <img src="/logo.png" alt="" width={size} height={size} />
      <Typography variant="h6" sx={{ fontWeight: 600 }}>
        Loctapus
      </Typography>
    </Box>
  );
}
