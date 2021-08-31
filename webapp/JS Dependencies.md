# JavaScript Dependencies
This is the current list of JavaScript (JS) dependencies which Thread uses. Please refer to this list and its links to ensure they are up-to-date.

If changing the JS script imports, please note order is important (and any required scripts of a library must be imported before the library-import itself).

| Library | Current Version (Date) | Library link(s) | Source (src) URL | Notes <sup>1</sup> |
| ----------- | ----------- | ----------- | ----------- | ----------- | 
| `jQuery` | v3.6.0<br/>(04 Mar '21) | [GitHub repo](https://github.com/jquery/jquery) | Obtained from [here](https://cdnjs.com/libraries/jquery) |  |
| `Bootstrap` | v5.1.0<br/>(05 Aug '21) | [GitHub repo](https://github.com/twbs/bootstrap) | Obtained from [here](https://cdnjs.com/libraries/bootstrap) | <ul><li>Also requires `bootstrap.min.css`.</li><li>Choose `bootstrap.bundle.min.js` to include `Popper`.</li><li>`bootstrap-glyphicon.min.css` is not required (despite being included via local files) because it is [deprecated](https://github.com/twbs/bootstrap/issues/18749). </li></ul> |
| `bootstrap-select` | v1.13.18<br/>(27 Jun '20)<br/>**Use v1.14.0-beta2** <sup>2</sup> | [GitHub repo](https://github.com/snapappointments/bootstrap-select) | Obtained from [here](https://cdnjs.com/libraries/bootstrap-select) | Requires jQuery, Popper, Bootstrap and `bootstrap-select.min.css`. |
| `Font Awesome` | v5.15.4<br/>(5 Aug '21) | [GitHub repo](https://github.com/FortAwesome/Font-Awesome) | Obtained from [here](https://cdnjs.com/libraries/font-awesome) | Not available for offline-Thread-use as `bootstrap-glyphicon.min.css` is used instead. |
| `pdfmake` | v0.2.2<br/>(03 Aug '21) | [GitHub repo](https://github.com/bpampuch/pdfmake) | Obtained from [here](https://cdnjs.com/libraries/pdfmake) | Also requires `vfs_fonts.js`. |
| `Popper` | - | - | - | <ul><li>Library imported via bundled `Bootstrap`.</li><li>Recording here as original release included local script of this.</li></ul> |
| `kanban` | - | - | - | <ul><li>Functionality not used.</li><li>Recording here as original release included local script of this.</li></ul> |

<sup>1</sup> If a library requirement is not in the table above, it can be found in the link for the library it is a requirement for.  

<sup>2</sup> A stable release is preferred over a beta release but (at time of writing) the stated beta version must be used. This is due to dropdowns not opening as older `bootstrap-select` versions use [incompatible](https://stackoverflow.com/a/65341807) `data-*` attributes. (The earliest beta version which caters for `data-bs-*` is the beta version stated here.)
