import htmx from "htmx.org";

window.htmx = htmx;

htmx.defineExtension('htmx-download', {
    onEvent: function (name, evt) {

        if (name === 'htmx:beforeRequest') {
            // Set the responseType to 'arraybuffer' to handle binary data
            evt.detail.xhr.responseType = 'arraybuffer';
        }

        if (name === 'htmx:beforeSwap') {
            const xhr = evt.detail.xhr;

            if (xhr.status === 200) {
                // Parse headers
                const headers = {};
                const headerStr = xhr.getAllResponseHeaders();
                const headerArr = headerStr.trim().split(/[\r\n]+/);
                headerArr.forEach((line) => {
                    const parts = line.split(": ");
                    const header = parts.shift().toLowerCase();
                    const value = parts.join(": ");
                    headers[header] = value;
                });

                // Extract filename
                let filename = 'downloaded_file.xlsx';
                if (headers['content-disposition']) {
                    const filenameMatch = headers['content-disposition'].match(/filename\*?=(?:UTF-8'')?"?([^;\n"]+)/i);
                    if (filenameMatch && filenameMatch[1]) {
                        filename = decodeURIComponent(filenameMatch[1].replace(/['"]/g, ''));
                    }
                }

                // Determine MIME type
                const mimetype = headers['content-type'] || 'application/octet-stream';

                // Create Blob
                const blob = new Blob([xhr.response], { type: mimetype });
                const url = URL.createObjectURL(blob);

                // Trigger download
                const link = document.createElement("a");
                link.style.display = "none";
                link.href = url;
                link.download = filename;
                document.body.appendChild(link);
                link.click();

                // Cleanup
                setTimeout(() => {
                    URL.revokeObjectURL(url);
                    link.remove();
                }, 100);

            } else {
                console.warn(`[htmx-download] Unexpected response status: ${xhr.status}`);
            }

            // Prevent htmx from swapping content
            evt.detail.shouldSwap = false;
        }
    },
});
