import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

/** Friendly empty state; the create CTA opens the same dialog as the header. */
export default function EmptyProjects({ onCreate }: { onCreate: () => void }) {
  return (
    <Card variant="outlined" sx={{ mt: 4, py: 6, px: 4 }}>
      <Stack spacing={2} sx={{ alignItems: "center" }}>
        <Typography variant="h6" sx={{ fontWeight: 600 }}>
          No projects yet
        </Typography>
        <Typography color="text.secondary">
          Create your first project to start uploading documents.
        </Typography>
        <Button variant="contained" onClick={onCreate}>
          Create project
        </Button>
      </Stack>
    </Card>
  );
}
