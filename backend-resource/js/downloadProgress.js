//Script for processing pull image request
$(function downloadProgress() {
    var currentDownloads
    currentDownloads = JSON.parse(sessionStorage.getItem('downloads'))
    if (currentDownloads == null) {
        currentDownloads = []
        sessionStorage.setItem('downloads', JSON.stringify(currentDownloads))
    }
    //Download button was pressed, initialize parameters
    $(".download-action").on('click', (e) => {
        var image_name = e.target.getAttribute("data-image-name")
        var instancetype = e.target.getAttribute("data-btn-type");
        var progress = undefined;
        var progress_bar = undefined;
        var state_text = undefined;
        //If new download was started, add it to mass
        if (currentDownloads.indexOf(image_name) == -1) {
            currentDownloads.push(image_name)
            sessionStorage.setItem('downloads', JSON.stringify(currentDownloads))
        }
        console.log(currentDownloads)
        //Initialize needed elements on exact tab where the download button was pressed:
        //state_text, progress, progress_bar
        if(instancetype == "ivi_download")
        {
            $('.text-ivi').each((i, obj) => {
                if (obj.getAttribute("data-image-name") === image_name) {
                    state_text = obj;
                }
            });
            $('.progress-ivi').each((i, obj) => {
                if (obj.getAttribute("data-image-name") === image_name) {
                    progress = obj;
                }
            });
            $('.progress-ivi').find('.progress-bar').each((i, obj) => {
                if (obj.getAttribute("data-image-name") === image_name) {
                    progress_bar = obj
                }
            });
        }
        if(instancetype == "cluster_download")
        {
            $('.text-cluster').each((i, obj) => {
              if (obj.getAttribute("data-image-name") === image_name) {
                state_text = obj;
              }
            });
            $('.progress-cluster').each((i, obj) => {
                if (obj.getAttribute("data-image-name") === image_name) {
                    progress = obj;
                }
            });
            $('.progress-cluster').find('.progress-bar').each((i, obj) => {
                if (obj.getAttribute("data-image-name") === image_name) {
                    progress_bar = obj
                }
            });
        }
        if(instancetype == "cockpit_download")
        {
            $('.text-cockpit').each((i, obj) => {
              if (obj.getAttribute("data-image-name") === image_name) {
                state_text = obj;
              }
            });
            $('.progress-cockpit').each((i, obj) => {
                if (obj.getAttribute("data-image-name") === image_name) {
                    progress = obj;
                }
            });
            $('.progress-cockpit').find('.progress-bar').each((i, obj) => {
                if (obj.getAttribute("data-image-name") === image_name) {
                    progress_bar = obj
                }
            });
        }
        //Disable download button and start to pull image, waiting for response to reload index page
        e.target.disabled = true;
        $.getJSON('/pull/' + image_name).complete(
            function(data) {
                response = $.parseJSON(data.responseText);
                    if (response.state == "Complete") {
                }
            }
        );
        //Open socket IO flask connection to get percent and state of downloading
        socket = io.connect("http://" + document.domain + ":" + location.port + "/" + image_name);
        socket.on("progress", (msg) => {
            var state = msg.text.split(":")[0];
            var width = parseInt(msg.text.split(":")[1]);
            //Make progress-bar visible if it was hidden and percent > 0
            if (state == "Downloading" && width > 0 && progress.style.visibility == 'hidden') {
                progress.style.visibility = 'visible';
                state_text.innerHTML = state
            }
            //Change state to Extracting if it is so
            if (state == "Extracting") {
                state_text.innerHTML = state
            }
            if (state == "Complete") {
                let currentDownloads = []
                currentDownloads = JSON.parse(sessionStorage.getItem('downloads'))
                var index = currentDownloads.indexOf(image_name)
                if (index != -1) {
                    currentDownloads.splice(index, 1)
                }
                console.log(currentDownloads)
                sessionStorage.setItem('downloads', JSON.stringify(currentDownloads))
                state_text.innerHTML = state
                setTimeout(function(){
                },2000);
                document.location.reload();
            }
            progress_bar.style.width = width + "%";
            progress_bar.innerHTML = width + "%";
            if (state == "Failure") {
                progress_bar.style.width = 0
                progress_bar.innerHTML = 0
                progress.style.visibility = 'hidden'
                progress_bar.style.visibility = 'hidden'
                e.target.disabled = false
                state_text.innerHTML = state
            }
        });
        return true;
    });
});