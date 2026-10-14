import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { statusChip } from "./uploadStatus";
import type { Upload } from "./uploadsApi";

/** The uploads table: one row per upload with its derived status chip. */
export default function UploadsTable({ uploads }: { uploads: Upload[] }) {
  return (
    <Box sx={{ mt: 3, overflowX: "auto" }}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>Filename</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Created</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {uploads.map((upload) => (
            <TableRow key={upload.id}>
              <TableCell>{upload.filename}</TableCell>
              <TableCell>
                <Chip size="small" {...statusChip(upload.status)} />
              </TableCell>
              <TableCell>{new Date(upload.created_at).toLocaleDateString()}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {uploads.length === 0 && (
        <Typography color="text.secondary" sx={{ mt: 2 }}>
          No documents uploaded yet.
        </Typography>
      )}
    </Box>
  );
}
