import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { Link as RouterLink } from "react-router";
import { statusChip } from "../uploads/uploadStatus";
import type { Upload } from "../uploads/uploadsApi";

/**
 * The project's source items in the CRUD template's table-in-card look. Every
 * item today is a file upload, so the Type column is a constant and each
 * filename links to the file-upload page - the item's type page; both grow
 * per type once a second source type exists.
 */
export default function SourceItemsTable({ items }: { items: Upload[] }) {
  return (
    <Card variant="outlined" sx={{ mt: 3, overflowX: "auto" }}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>Filename</TableCell>
            <TableCell>Type</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Created</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.id}>
              <TableCell>
                <Link component={RouterLink} to={`/projects/${item.project_id}/sources/upload`}>
                  {item.filename}
                </Link>
              </TableCell>
              <TableCell>File upload</TableCell>
              <TableCell>
                <Chip size="small" {...statusChip(item.status)} />
              </TableCell>
              <TableCell>{new Date(item.created_at).toLocaleDateString()}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {items.length === 0 && (
        <Typography color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
          No source items yet.
        </Typography>
      )}
    </Card>
  );
}
