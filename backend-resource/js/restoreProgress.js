//Restore state of download buttons after refreshing page or changing tab
function restoreDownloadsAfterPageReload(idTab) {
    var tab = idTab
    var currentDownloads
    if (sessionStorage.getItem('downloads') == null) {
        sessionStorage.setItem('downloads', JSON.stringify([]));
        currentDownloads = []
        currentDownloads = JSON.parse(sessionStorage.getItem('downloads'))
        console.log(currentDownloads)
    } else {
        currentDownloads = []
        currentDownloads = JSON.parse(sessionStorage.getItem('downloads'))
        console.log(currentDownloads)
        if (tab == null) {
            console.log("Window hash is: " + window.location.hash)
            switch (window.location.hash) {
                case "#ivi":
                    tab = "ivi-tab"
                    console.log("Get ivi tab from switch")
                    break
                case "#cluster":
                    tab = "cluster-tab"
                    console.log("Get cluster tab from switch")
                    break
                case "#cockpit":
                    tab = "cockpit-tab"
                    console.log("Get cockpit tab from switch")
                    break
                default:
                    $("#h-navbar > ul > li").each(function() {
                        if ($(this).hasClass("active")) {
                            tab = this.id
                            console.log("Tab was null after reload")
                        }
                    });
            }
        }
        console.log(tab)
        //Set state clicked to all active download buttons from currentDownloads
        currentDownloads.forEach(element => {
            console.log(element)
            switch (tab) {
                case "ivi-tab":
                    console.log("I am in ivi, try to find buttons")
                    $('.btn').each((i, obj) => {
                        if (obj.getAttribute("data-btn-type") === "ivi_download"
                         && obj.getAttribute("data-image-name") === element) {
                            obj.click()
                        }
                    });
                    break
                case "cluster-tab":
                    console.log("I am in cluster, try to find buttons")
                    $('.btn').each((i, obj) => {
                        if (obj.getAttribute("data-btn-type") === "cluster_download"
                         && obj.getAttribute("data-image-name") === element) {
                            obj.click()
                        }
                    });
                    break
                case "cockpit-tab":
                    console.log("I am in cockpit, try to find buttons")
                    $('.btn').each((i, obj) => {
                        if (obj.getAttribute("data-btn-type") === "cockpit_download"
                         && obj.getAttribute("data-image-name") === element) {
                            obj.click()
                        }
                    });
                    break
                default:
                    console.log("Buttons were not found")
            }
        });
    }
}